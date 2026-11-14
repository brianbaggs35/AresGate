"""The assistant: what it is shown, how a reply is read, the lookups it asks for, what it cites,
and what is kept of a conversation. The provider is a server on this machine that says what it is
told to, one reply for each request."""

import json
import re
from collections.abc import Callable
from ipaddress import ip_address

import anyio
import anyio.to_thread
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat, tools
from app.ai.gateway import Context
from app.config import Settings
from app.models import (
    AiCall,
    AiConversation,
    AiMessage,
    Device,
    DeviceAddress,
    IntegrationConnection,
)
from tests.stubs import Answer as Reply
from tests.stubs import Handler, Seen, Serve
from tests.test_ai_gateway import Log, anthropic_says, context
from tests.test_ai_service import NOW
from tests.test_ai_triage import ATTACKER, DEVICE, incident, prompt_of, ready, signals


def reply(**changes: object) -> str:
    """What a model says: by default an answer with nothing looked up and nothing cited."""
    said: dict[str, object] = {"lookups": [], "answer": "All quiet.", "cites": []}
    said.update(changes)
    return json.dumps(said)


def look(tool: str, **args: object) -> dict[str, object]:
    return {"tool": tool, "id": None, "name": None, "hours": None, "limit": None, **args}


class Scripted:
    """A provider that gives these replies one after another, and keeps what it was asked."""

    def __init__(self, *replies: str | Callable[[str], str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, seen: Seen) -> Reply:
        prompt = prompt_of(seen)
        self.prompts.append(prompt)
        step = self.replies.pop(0)
        return anthropic_says(step if isinstance(step, str) else step(prompt))(seen)


def tool(name: str) -> tools.Tool:
    found = tools.by_name(name)
    assert found is not None
    return found


def conversation(session: Session) -> AiConversation:
    row = AiConversation(title="t", created_at=NOW, updated_at=NOW)
    session.add(row)
    session.flush()
    return row


def say(
    session: Session,
    where: Context,
    row: AiConversation,
    text: str,
    page: chat.Page | None = None,
) -> list[AiMessage]:
    async def from_a_thread() -> None:
        await anyio.to_thread.run_sync(chat.say, session, where, row, text, NOW, page)

    anyio.run(from_a_thread)
    return chat.messages(session, row)


def talk(
    session: Session,
    settings: Settings,
    serve: Serve,
    provider: Handler,
    text: str = "Anything?",
    page: chat.Page | None = None,
) -> tuple[AiConversation, list[AiMessage]]:
    server = serve(provider)
    ready(session, settings)
    row = conversation(session)
    return row, say(session, context(settings, Log(), server.url), row, text, page)


class TestReadingAReply:
    def test_an_answer_with_nothing_to_look_up(self) -> None:
        step = chat.parse(reply(answer="Fine.", cites=["incident 3"]))

        assert step == chat.Step(lookups=[], answer="Fine.", cites=["incident 3"])

    def test_what_it_wants_looked_up_is_read_with_the_arguments_that_are_numbers_and_words(
        self,
    ) -> None:
        step = chat.parse(
            reply(
                lookups=[
                    look("incident", id=4),
                    look("device", name="  nas  "),
                    look("alerts", hours=6.0, limit=3),
                ],
                answer="",
            )
        )

        assert step is not None
        assert step.lookups == [
            chat.Lookup(tool("incident"), tools.Args(id=4)),
            chat.Lookup(tool("device"), tools.Args(name="nas")),
            chat.Lookup(tool("alerts"), tools.Args(hours=6, limit=3)),
        ]

    def test_a_tool_that_is_not_on_the_list_is_ignored(self) -> None:
        step = chat.parse(
            reply(lookups=[look("delete_incident", id=4), "open_incidents", 7, look("alerts")])
        )

        assert step is not None
        assert [lookup.tool.name for lookup in step.lookups] == ["alerts"]

    def test_arguments_that_are_not_what_they_should_be_are_left_empty(self) -> None:
        step = chat.parse(reply(lookups=[look("incident", id=True, name=7, hours="3", limit=None)]))

        assert step is not None
        assert step.lookups == [chat.Lookup(tool("incident"), tools.Args())]

    def test_no_more_than_four_lookups_are_kept(self) -> None:
        step = chat.parse(reply(lookups=[look("alerts", hours=n) for n in range(1, 9)]))

        assert step is not None
        assert [lookup.args.hours for lookup in step.lookups] == [1, 2, 3, 4]

    def test_things_that_are_not_text_are_left_out(self) -> None:
        step = chat.parse(json.dumps({"lookups": "none", "answer": 7, "cites": ["a", 3, None]}))

        assert step == chat.Step(lookups=[], answer=None, cites=["a"])

    def test_a_code_fence_or_a_sentence_around_it_is_forgiven(self) -> None:
        inner = reply(answer="Yes.")

        assert chat.parse(f"```json\n{inner}\n```") == chat.parse(inner)
        assert chat.parse(f"Here you go: {inner} Hope that helps.") == chat.parse(inner)

    @pytest.mark.parametrize("text", ["", "no json here", "[1, 2]", '"x"', "{not json}"])
    def test_what_is_not_an_object_is_not_a_reply(self, text: str) -> None:
        assert chat.parse(text) is None


class TestTheTitle:
    def test_it_is_the_first_line_cut_short(self) -> None:
        assert chat.title_of("  What happened?\nAnd why?") == "What happened?"
        assert len(chat.title_of("x" * 500)) <= chat.MAX_TITLE

    def test_a_blank_text_still_has_a_title(self) -> None:
        assert chat.title_of("   ") == "Conversation"


class TestAnswering:
    def test_a_question_it_can_answer_from_the_overview_takes_one_request(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3)
        session.commit()
        provider = Scripted(reply(answer="One thing needs you."))

        row, history = talk(session, settings, serve, provider, "What needs me?")

        assert [(m.role, m.text, m.ok) for m in history] == [
            ("user", "What needs me?", True),
            ("assistant", "One thing needs you.", True),
        ]
        [prompt] = provider.prompts
        assert "Right now 1 incidents need someone (1 high)." in prompt
        assert "The owner asks: What needs me?" in prompt
        assert "earlier in this conversation" not in prompt
        [call] = session.scalars(select(AiCall)).all()
        assert (call.purpose, call.about) == ("chat", f"chat {row.id}")
        assert history[1].call_ids == [call.id]
        assert history[1].lookups == []
        assert history[1].cites == []
        assert found.id
        assert row.updated_at == NOW

    def test_the_overview_says_when_nothing_needs_anyone_and_what_is_failing(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        session.add_all(
            [
                IntegrationConnection(integration="ntopng", connection="api", base_url="https://t"),
                IntegrationConnection(
                    integration="opnsense", connection="api", base_url="https://f", last_error="no"
                ),
            ]
        )
        session.commit()
        provider = Scripted(reply())

        talk(session, settings, serve, provider)

        assert (
            "Right now no incident needs anyone. 2 integrations are connected, 1 of them"
            in (provider.prompts[0])
        )

    def test_it_looks_things_up_and_answers_from_what_was_found_citing_only_what_it_saw(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3, title="Guessing at ssh")
        session.commit()
        provider = Scripted(
            reply(lookups=[look("open_incidents", limit=3)], answer=""),
            reply(
                answer=f"Look at [incident {found.id}].",
                cites=[f"incident {found.id}", "[Incident 999]", "integration nothing", "x"],
            ),
        )

        row, history = talk(session, settings, serve, provider, "What needs me?")

        assistant = history[1]
        assert assistant.text == f"Look at [incident {found.id}]."
        assert assistant.lookups == [{"tool": "open_incidents", "summary": "1 open incident"}]
        assert assistant.cites == [
            {"kind": "incident", "key": str(found.id), "label": f"Incident {found.id}"}
        ]
        first, second = provider.prompts
        assert "<data" not in first
        assert '<data label="open incidents limit 3">' in second
        assert f"[incident {found.id}] high" in second
        assert "Guessing at ssh" in second
        calls = session.scalars(select(AiCall).order_by(AiCall.id)).all()
        assert [call.about for call in calls] == [f"chat {row.id}"] * 2
        assert assistant.call_ids == [call.id for call in calls]

    def test_a_device_it_looked_up_can_be_cited_but_one_it_did_not_see_cannot(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        nas = Device(
            mac="aa:bb:cc:00:00:01",
            hostname="vault",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        session.add(nas)
        session.commit()
        provider = Scripted(
            reply(lookups=[look("device", name="vault")], answer=""),
            reply(
                answer=f"It is [device {nas.id}].",
                cites=[f"device {nas.id}", "device 999", f"Device {nas.id}"],
            ),
        )

        _, history = talk(session, settings, serve, provider, "What is vault?")

        assert history[1].cites == [{"kind": "device", "key": str(nas.id), "label": "vault"}]
        # The provider is shown the device's number and a stand-in for its name, never the name.
        assert f"[device {nas.id}] NAME_" in provider.prompts[1]
        assert "vault" not in provider.prompts[1]
        assert "[device 12]" in chat.SYSTEM

    def test_the_same_lookup_asked_twice_is_run_once(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        incident(session)
        session.commit()
        provider = Scripted(
            reply(lookups=[look("open_incidents")], answer=""),
            reply(lookups=[look("open_incidents"), look("integrations")], answer=""),
            reply(answer="Done."),
        )

        _, history = talk(session, settings, serve, provider)

        assert history[1].text == "Done."
        assert [lookup["tool"] for lookup in history[1].lookups] == [
            "open_incidents",
            "integrations",
        ]
        assert provider.prompts[2].count("open incidents") == 1

    def test_the_last_time_it_has_to_answer_and_is_told_so(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        more = reply(lookups=[look("alerts")], answer="")
        provider = Scripted(more, more, reply(lookups=[look("integrations")], answer=""))

        _, history = talk(session, settings, serve, provider)

        assert [prompt.count(chat.NO_MORE) for prompt in provider.prompts] == [0, 0, 1]
        assert history[1].ok is False
        assert history[1].text == "The AI did not give an answer. Ask again."
        assert len(history[1].call_ids) == chat.MAX_ROUNDS

    def test_a_last_reply_that_does_answer_is_taken_even_if_it_asks_for_more(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        more = reply(lookups=[look("alerts")], answer="")
        provider = Scripted(more, more, reply(lookups=[look("integrations")], answer="Enough."))

        _, history = talk(session, settings, serve, provider)

        assert (history[1].ok, history[1].text) == (True, "Enough.")

    def test_a_reply_that_cannot_be_read_says_so(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        _, history = talk(session, settings, serve, Scripted("I would rather not."))

        assert history[1].ok is False
        assert history[1].text == "The AI's answer could not be read. Ask again."

    def test_a_provider_that_fails_says_why(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        _, history = talk(
            session, settings, serve, lambda seen: Reply(status=500, body="{}"), "Anything?"
        )

        assert history[1].ok is False
        assert history[1].text
        assert history[1].call_ids != []

    def test_with_ai_off_it_says_so_and_asks_nobody(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(Scripted())
        row = conversation(session)

        history = say(session, context(settings, Log(), server.url), row, "Anything?")

        assert history[1].ok is False
        assert history[1].text.startswith("AI is turned off.")
        assert history[1].call_ids == []
        assert session.scalars(select(AiCall)).all() == []

    def test_a_provider_that_may_not_see_addresses_is_shown_stand_ins_and_the_owner_the_real_ones(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        from app.models import AiSettings

        found = incident(session)
        signals(session, found)
        session.commit()

        def names_the_address(prompt: str) -> str:
            stand_in = re.search(r"EXT_\d+", prompt)
            return reply(answer=f"{stand_in.group(0) if stand_in else 'nothing'} scanned you.")

        provider = Scripted(
            reply(lookups=[look("incident", id=found.id)], answer=""), names_the_address
        )
        server = serve(provider)
        ready(session, settings, level="strict")
        assert session.get(AiSettings, 1) is not None
        row = conversation(session)

        history = say(
            session,
            context(settings, Log(), server.url),
            row,
            f"What is {ATTACKER} doing to {DEVICE}?",
        )

        prompts = " ".join(provider.prompts)
        assert ATTACKER not in prompts
        assert DEVICE not in prompts
        assert re.search(r"The owner asks: What is EXT_\d+ doing to HOST_\d+\?", prompts)
        assert history[1].text == f"{ATTACKER} scanned you."
        # What the owner wrote is kept as they wrote it.
        assert history[0].text == f"What is {ATTACKER} doing to {DEVICE}?"


class TestTheConversationSoFar:
    def test_the_model_is_shown_what_was_said_before_but_not_answers_that_failed(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        provider = Scripted(reply(answer="First answer."), reply(answer="Second answer."))
        server = serve(provider)
        ready(session, settings)
        row = conversation(session)
        where = context(settings, Log(), server.url)
        session.add_all(
            [
                AiMessage(
                    conversation_id=row.id, role="user", text="Broken question", created_at=NOW
                ),
                AiMessage(
                    conversation_id=row.id,
                    role="assistant",
                    text="It went wrong",
                    ok=False,
                    created_at=NOW,
                ),
            ]
        )

        say(session, where, row, "First?")
        history = say(session, where, row, "Second?")

        second = provider.prompts[1]
        assert "Owner: First?" in second
        assert "You: First answer." in second
        assert "It went wrong" not in second
        assert "Broken question" in second
        assert history[-1].text == "Second answer."

    def test_only_the_end_of_a_long_conversation_is_shown(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        provider = Scripted(reply())
        server = serve(provider)
        ready(session, settings)
        row = conversation(session)
        for number in range(chat.HISTORY * 2):
            session.add(
                AiMessage(
                    conversation_id=row.id,
                    role="user" if number % 2 == 0 else "assistant",
                    text=f"line {number}",
                    created_at=NOW,
                )
            )

        say(session, context(settings, Log(), server.url), row, "Now?")

        shown = provider.prompts[0]
        assert "line 5" not in shown
        assert "line 6" in shown
        assert "line 11" in shown


def suggest(
    kind: str, target: str, value: str | None = None, note: str | None = None
) -> dict[str, str | None]:
    return {"kind": kind, "target": target, "value": value, "note": note}


class TestSuggestingWhatToDo:
    """The assistant may suggest what the owner could do, and the owner presses the button."""

    def test_a_suggestion_names_what_it_is_about_and_says_what_it_would_do(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3)
        session.commit()
        provider = Scripted(
            reply(lookups=[look("incident", id=found.id)], answer=""),
            reply(
                answer="Dismiss it.",
                actions=[
                    suggest("open", f"incident {found.id}"),
                    suggest("status", f"[incident {found.id}]", "Dismissed"),
                    suggest(
                        "verdict", f"incident {found.id}", "not_suspicious", "A known scanner."
                    ),
                    suggest("open", "logs", " ET SCAN "),
                ],
            ),
        )

        _, history = talk(session, settings, serve, provider)

        assert history[1].actions == [
            {
                "kind": "open",
                "target_kind": "incident",
                "target_key": str(found.id),
                "value": None,
                "note": None,
                "label": f"Open Incident {found.id}",
            },
            {
                "kind": "status",
                "target_kind": "incident",
                "target_key": str(found.id),
                "value": "dismissed",
                "note": None,
                "label": f"Dismiss Incident {found.id}",
            },
            {
                "kind": "verdict",
                "target_kind": "incident",
                "target_key": str(found.id),
                "value": "not_suspicious",
                "note": "A known scanner.",
                "label": f"Call Incident {found.id} not suspicious",
            },
        ]

    def test_at_most_three_and_each_once(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3)
        session.commit()
        name = f"incident {found.id}"
        provider = Scripted(
            reply(lookups=[look("incident", id=found.id)], answer=""),
            reply(
                actions=[
                    suggest("status", name, "resolved"),
                    suggest("status", name, "resolved"),
                    suggest("status", name, "investigating"),
                    suggest("status", name, "open"),
                    suggest("status", name, "dismissed"),
                ]
            ),
        )

        _, history = talk(session, settings, serve, provider)

        assert [item["value"] for item in history[1].actions] == [
            "resolved",
            "investigating",
            "open",
        ]

    @pytest.mark.parametrize(
        "suggestion",
        [
            suggest("status", "incident 999", "dismissed"),
            suggest("status", "device 1", "dismissed"),
            suggest("status", "INCIDENT", "dismissed"),
            suggest("verdict", "incident 999", "threat"),
            suggest("verdict", "incident @", "unknown"),
            suggest("verdict", "incident @", None),
            suggest("status", "incident @", "deleted"),
            suggest("open", "logs", None),
            suggest("open", "logs", "   "),
            suggest("open", "incident 999"),
            suggest("delete", "incident @", "all"),
        ],
        ids=[
            "an incident it did not see",
            "a status on a device",
            "no number",
            "a verdict on one it did not see",
            "a verdict that is not one",
            "no verdict",
            "a status that is not one",
            "a search of nothing",
            "a search of spaces",
            "opening what it did not see",
            "a kind that is not offered",
        ],
    )
    def test_anything_it_may_not_suggest_is_dropped(
        self,
        session: Session,
        settings: Settings,
        serve: Serve,
        suggestion: dict[str, str | None],
    ) -> None:
        found = incident(session, severity=3)
        session.commit()
        # The incident the model was shown, named as the model names it.
        target = (suggestion["target"] or "").replace("@", str(found.id))
        suggestion = {**suggestion, "target": target}
        provider = Scripted(
            reply(lookups=[look("incident", id=found.id)], answer=""),
            reply(actions=[suggestion]),
        )

        _, history = talk(session, settings, serve, provider)

        assert history[1].actions == []

    def test_a_reply_that_says_nothing_of_actions_suggests_none(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        _, history = talk(session, settings, serve, Scripted(reply()))

        assert history[1].actions == []

    def test_a_reply_with_odd_actions_is_still_read(self) -> None:
        step = chat.parse(
            reply(actions=["x", {"kind": 3, "target": "a"}, {"kind": "open", "target": "logs"}])
        )

        assert step is not None
        assert step.actions == [chat.Suggestion("open", "logs", None, None)]
        assert chat.parse(reply(actions="none")) == chat.Step(
            lookups=[], answer="All quiet.", cites=[], actions=[]
        )


class TestThePageTheOwnerIsOn:
    def test_the_incident_on_screen_is_looked_up_before_anything_is_asked(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3, title="Guessing at ssh")
        session.commit()
        provider = Scripted(reply(answer="It is a scan."))

        _, history = talk(
            session,
            settings,
            serve,
            provider,
            "What is this?",
            chat.Page("incident", id=found.id),
        )

        (prompt,) = provider.prompts
        assert f"The owner has the page of incident {found.id} open." in prompt
        assert f'<data label="incident id {found.id}">' in prompt
        assert "Guessing at ssh" in prompt
        assert history[1].lookups == [{"tool": "incident", "summary": f"incident {found.id}"}]

    def test_it_can_be_cited_and_suggested_about_without_asking_for_it(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        found = incident(session, severity=3)
        session.commit()
        provider = Scripted(
            reply(
                answer="Close it.",
                cites=[f"incident {found.id}"],
                actions=[suggest("status", f"incident {found.id}", "resolved")],
            )
        )

        _, history = talk(
            session, settings, serve, provider, "Close this?", chat.Page("incident", id=found.id)
        )

        assert [item["key"] for item in history[1].cites] == [str(found.id)]
        assert [item["label"] for item in history[1].actions] == [
            f"Mark Incident {found.id} as resolved"
        ]

    def test_the_device_on_screen_is_found_by_its_address(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        nas = Device(mac="aa:bb:cc:00:00:01", hostname="vault", first_seen_at=NOW, last_seen_at=NOW)
        session.add(nas)
        session.flush()
        session.add(
            DeviceAddress(
                device_id=nas.id, address=ip_address(DEVICE), first_seen_at=NOW, last_seen_at=NOW
            )
        )
        session.commit()
        provider = Scripted(reply())

        talk(session, settings, serve, provider, "Is it ok?", chat.Page("device", address=DEVICE))

        (prompt,) = provider.prompts
        assert f'<data label="device id {nas.id}">' in prompt
        assert f"[device {nas.id}]" in prompt
        assert DEVICE not in prompt
        assert "vault" not in prompt

    def test_the_device_on_screen_is_found_by_its_number_too(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        nas = Device(mac="aa:bb:cc:00:00:01", hostname="vault", first_seen_at=NOW, last_seen_at=NOW)
        session.add(nas)
        session.commit()
        provider = Scripted(reply())

        talk(session, settings, serve, provider, "Is it ok?", chat.Page("device", id=nas.id))

        assert f'<data label="device id {nas.id}">' in provider.prompts[0]

    @pytest.mark.parametrize(
        "page",
        [
            chat.Page("device", address="not an address"),
            chat.Page("device", address="10.9.9.9"),
            chat.Page("device"),
            chat.Page("incident"),
            chat.Page("logs"),
        ],
        ids=["a bad address", "an address no device has", "no device", "no incident", "the logs"],
    )
    def test_a_page_that_names_nothing_to_look_up_looks_up_nothing(
        self, session: Session, settings: Settings, serve: Serve, page: chat.Page
    ) -> None:
        provider = Scripted(reply())

        _, history = talk(session, settings, serve, provider, "What is this?", page)

        assert "<data" not in provider.prompts[0]
        assert history[1].lookups == []

    def test_the_search_on_screen_is_told_to_the_model_without_the_names_it_may_not_see(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        session.add(
            Device(mac="aa:bb:cc:00:00:01", hostname="vault", first_seen_at=NOW, last_seen_at=NOW)
        )
        session.commit()
        provider = Scripted(reply(), reply(), reply(), reply())
        page = chat.Page("logs", query="source:wazuh vault")

        talk(session, settings, serve, provider, "Why so many?", page)
        talk(
            session,
            settings,
            serve,
            provider,
            "And?",
            chat.Page("incidents", query="severity:high"),
        )
        talk(session, settings, serve, provider, "And?", chat.Page("logs"))
        talk(session, settings, serve, provider, "And?", chat.Page("other", title="Assets"))

        first, second, third, fourth = provider.prompts
        assert "The owner is on the Logs page, searching for: source:wazuh NAME_" in first
        assert "vault" not in first
        assert "The owner is on the list of incidents, searching for: severity:high." in second
        assert "The owner is on the Logs page." in third
        assert "The owner is on the Assets page." in fourth

    @pytest.mark.parametrize(
        "page",
        [None, chat.Page("incident"), chat.Page("other"), chat.Page("mystery", title="x")],
        ids=["none", "incident with no number", "other with no title", "a kind it does not know"],
    )
    def test_without_a_page_that_says_something_it_says_nothing(
        self, session: Session, settings: Settings, serve: Serve, page: chat.Page | None
    ) -> None:
        provider = Scripted(reply())

        talk(session, settings, serve, provider, "Anything?", page)

        assert "owner has the page" not in provider.prompts[0]
        assert "The owner is on" not in provider.prompts[0]
