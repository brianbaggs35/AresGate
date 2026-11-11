"""AI triage: what the AI is asked about an incident, how its answer is read and kept, which
incidents are read without being asked, and the loop that reads them. The provider is a server on
this machine that answers the way Anthropic's API does."""

import asyncio
import itertools
import json
import logging
import re
from collections.abc import Callable
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

import anyio
import anyio.to_thread
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import catalog, gateway, run, service, triage
from app.ai.gateway import Answer, Unavailable
from app.ai.redaction import Level, Redactor
from app.config import Settings
from app.incidents import queries
from app.intel import store as intel_store
from app.intel import subjects, virustotal
from app.models import (
    CLASSES,
    USAGE_LEVELS,
    AiCall,
    AiTriage,
    Device,
    DeviceAddress,
    Incident,
    IncidentSignal,
)
from tests.stubs import Handler, Seen, Serve
from tests.test_ai_gateway import Log, anthropic_says, context, turned_on
from tests.test_ai_service import NOW, saved
from tests.test_incidents_search import incident as make_incident

ATTACKER = "203.0.113.5"

DEVICE = "192.168.1.20"
MINUTE = timedelta(minutes=1)
events = itertools.count(1)


def save_report(
    session: Session, address: IPv4Address | IPv6Address, report: virustotal.Report
) -> None:
    """Keeps what VirusTotal reported of an address, as the address's answer."""
    intel_store.keep(
        session,
        virustotal.PROVIDER,
        subjects.of_address(address),
        virustotal.Reported(report),
        report.analysed_at,
    )


def incident(session: Session, **changes: object) -> Incident:
    fields: dict[str, object] = {
        "subject": ATTACKER,
        "title": f"Scan from {ATTACKER}",
        "severity": 2,
        "confidence": 55,
        "reasons": [{"rule": "scan", "points": 30, "text": f"{ATTACKER} touched 12 ports"}],
        "first_seen_at": NOW - 40 * MINUTE,
        "last_seen_at": NOW - 5 * MINUTE,
        "signal_count": 3,
        "sources": ["opnsense", "wazuh"],
        "addresses": [ip_address(ATTACKER), ip_address(DEVICE)],
        "ports": [22, 80],
        "activities": ["scan"],
        "waves": 2,
    }
    fields.update(changes)
    return make_incident(session, str(fields.pop("subject")), **fields)


def signals(session: Session, found: Incident, count: int = 3, **changes: object) -> None:
    for n in range(count):
        fields: dict[str, Any] = {
            "incident_id": found.id,
            "event_id": next(events),
            "occurred_at": NOW - (count - n) * MINUTE,
            "source": "opnsense",
            "kind": "alert",
            "severity": 2,
            "summary": f"Scan {n}",
            "signature": f"ET SCAN {n}",
            "src_address": ip_address(ATTACKER),
            "src_port": 4000 + n,
            "dst_address": ip_address(DEVICE),
            "dst_port": 22,
            "protocol": "tcp",
        }
        fields.update(changes)
        session.add(IncidentSignal(**fields))
    session.flush()


def reading(**changes: object) -> dict[str, object]:
    said: dict[str, object] = {
        "classification": "probe",
        "confidence": 91,
        "headline": "An internet scanner looked at one device",
        "story": "It tried a few ports. Nothing got in.",
        "checks": ["Look at the firewall rules for port 22", "Nothing else needed"],
        "observations": ["One address tried ports 22 and 80", "No data came back"],
        "verdict": "low_priority",
        "verdict_reason": "Routine background scanning.",
    }
    said.update(changes)
    return said


def prompt_of(seen: Seen) -> str:
    return str(json.loads(seen.body)["messages"][0]["content"])


def reads_it(**changes: object) -> Handler:
    """A provider that says what it made of it, using the stand-in it was shown for the device."""

    def handle(seen: Seen):
        found = re.search(r"HOST_\d+", prompt_of(seen))
        stand_in = found.group(0) if found else "nothing"
        said = reading(story=f"{stand_in} was scanned.", **changes)
        return anthropic_says(json.dumps(said))(seen)

    return handle


def ready(session: Session, settings: Settings, *, level: str = "balanced") -> None:
    saved(session, settings, catalog.ANTHROPIC)
    turned_on(session, "anthropic", level)


def with_level(session: Session, usage_level: str) -> None:
    service.usage(session, NOW).usage_level = usage_level
    session.commit()


def asked_about(session: Session, found: Incident, *, ok: bool, minutes_ago: int) -> None:
    session.add(
        AiCall(
            occurred_at=NOW - minutes_ago * MINUTE,
            purpose="triage",
            about=triage.about(found.id),
            provider="anthropic",
            model="claude-haiku-5-5",
            level="balanced",
            ok=ok,
            prompt="x",
        )
    )
    session.flush()


def kept(session: Session, found: Incident, **changes: object) -> AiTriage:
    fields: dict[str, Any] = {
        "incident_id": found.id,
        "read_at": NOW - 3 * 60 * MINUTE,
        "signals_read": found.signal_count,
        "classification": "probe",
        "confidence": 80,
        "headline": "h",
        "story": "s",
        "checks": [],
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
    }
    fields.update(changes)
    row = AiTriage(**fields)
    session.add(row)
    session.flush()
    return row


class TestWhatTheAiIsAsked:
    def prompt(self, session: Session, found: Incident, level: Level = Level.BALANCED) -> str:
        names = [device.hostname for _, device in queries.devices(session, found)]
        redactor = Redactor(session, level, NOW, names=[name for name in names if name])
        return redactor.finish(triage.prompt_for(session, found, redactor))

    def test_it_is_told_what_the_incident_is(self, session: Session) -> None:
        found = incident(session, banned=True, verdict_counts={"low_priority": 1})
        signals(session, found)

        said = self.prompt(session, found)

        assert f"Incident: Scan from {ATTACKER}" in said
        assert f"About: {ATTACKER}" in said
        assert "Severity of the worst signal: medium" in said
        assert "confidence that it is a real attack: 55 of 100" in said
        assert "reported by opnsense, wazuh" in said
        assert "Kinds of activity: scan" in said
        assert "2 separate bursts" in said
        assert "Destination ports touched: 22, 80" in said
        assert "banned the address: yes" in said
        assert "already said of some of its signals: 1 low_priority" in said
        assert "12 ports" in said
        assert '<data label="signals oldest first">' in said
        assert "ET SCAN 0" in said

    def test_a_quiet_one_has_only_what_it_has(self, session: Session) -> None:
        found = incident(
            session,
            activities=[],
            waves=1,
            ports=[],
            reasons=[],
            sources=[],
            first_seen_at=NOW - timedelta(hours=60),
            addresses=[],
        )

        said = self.prompt(session, found)

        assert "Kinds of activity" not in said
        assert "separate bursts" not in said
        assert "Destination ports" not in said
        assert "Why AresGate's rules" not in said
        assert "reported by nobody" in said
        assert "over 2 days" in said
        assert "banned the address: no" in said

    @pytest.mark.parametrize(
        ("minutes", "said"),
        [(0, "1 minutes"), (59, "59 minutes"), (125, "2 h 5 min"), (60 * 47, "47 h 0 min")],
    )
    def test_how_long_it_went_on_is_said_in_a_unit_that_fits(
        self, session: Session, minutes: int, said: str
    ) -> None:
        found = incident(session, last_seen_at=NOW, first_seen_at=NOW - minutes * MINUTE)

        assert f"(over {said})" in self.prompt(session, found)

    def test_the_devices_involved_are_named_by_stand_in_and_the_name_is_hidden_everywhere(
        self, session: Session
    ) -> None:
        found = incident(session, title="Scan of nas.example.home")
        nas = Device(
            mac="aa:bb:cc:00:11:22",
            hostname="nas.example.home",
            vendor="Synology",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        bare = Device(mac="aa:bb:cc:00:11:33", first_seen_at=NOW, last_seen_at=NOW)
        session.add_all([nas, bare])
        session.flush()
        session.add_all(
            [
                DeviceAddress(
                    device_id=nas.id,
                    address=ip_address(DEVICE),
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                ),
                DeviceAddress(
                    device_id=bare.id,
                    address=ip_address("192.168.1.21"),
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                ),
            ]
        )
        found.addresses = [ip_address(ATTACKER), ip_address(DEVICE), ip_address("192.168.1.21")]
        session.flush()
        signals(session, found, 1, summary="Login to nas.example.home failed")

        said = self.prompt(session, found)

        assert "nas.example.home" not in said
        assert DEVICE not in said
        assert "192.168.1.21" not in said
        assert "NAME_" in said
        assert ", made by Synology" in said
        assert ": unnamed" in said
        assert ATTACKER in said

    def test_strict_hides_the_attacker_too(self, session: Session) -> None:
        found = incident(session)
        signals(session, found)

        said = self.prompt(session, found, Level.STRICT)

        assert ATTACKER not in said
        assert "EXT_" in said

    def test_a_long_timeline_is_the_first_signals_and_the_last(self, session: Session) -> None:
        found = incident(session, signal_count=45)
        signals(session, found, 45)

        said = self.prompt(session, found)

        assert "ET SCAN 9" in said
        assert "ET SCAN 10 " not in said
        assert "... 15 more kinds in between ..." in said
        assert "ET SCAN 25" in said
        assert "ET SCAN 44" in said

    def test_the_same_thing_said_again_and_again_is_one_line_with_how_often(
        self, session: Session
    ) -> None:
        found = incident(session, signal_count=40)
        signals(session, found, 40, signature="ET SCAN same", summary="same")
        signals(session, found, 1, signature="ET SCAN once", summary="once")

        said = self.prompt(session, found)

        assert said.count("ET SCAN same") == 1
        assert ", 40 times, opnsense alert" in said
        assert said.count("ET SCAN once") == 1

    def test_a_signal_says_where_from_and_to_and_what_the_owner_said_of_it(
        self, session: Session
    ) -> None:
        found = incident(session)
        signals(session, found, 1, verdict="low_priority", signature=None, summary="A summary")
        signals(session, found, 1, src_port=None, dst_port=None, protocol=None, dst_address=None)
        signals(session, found, 1, src_address=None, dst_port=None, protocol=None)

        said = self.prompt(session, found)

        assert f"{ATTACKER}:4000 -> HOST_" in said
        assert "[owner: low_priority]" in said
        assert "A summary" in said
        assert f"{ATTACKER} -> ?" in said
        assert "? -> HOST_" in said

    def test_a_signal_with_no_address_has_none_in_the_line(self, session: Session) -> None:
        found = incident(session)
        signals(
            session,
            found,
            1,
            src_address=None,
            src_port=None,
            dst_address=None,
            dst_port=None,
            protocol=None,
        )

        assert " -> " not in self.prompt(session, found)

    def test_it_is_told_what_the_programs_said_of_the_traffic_beyond_the_basics(
        self, session: Session
    ) -> None:
        found = incident(session)
        flow = {
            "duration": 61,
            "client": {"address": ATTACKER, "name": "scanner", "location": "remote"},
            "server": {
                "address": DEVICE,
                "port": 22,
                "service": "ssh",
                "country": "NL",
                "blacklisted": True,
            },
        }
        signals(
            session,
            found,
            1,
            source="ntopng",
            evidence={
                "facts": [],
                "tags": ["Brute Force"],
                "mitre": [{"id": "T1110", "tactic": "Credential Access", "technique": "Brute"}],
                "indicators": [{"kind": "hostname", "value": "scanner.example.net"}],
                "traffic": {"bytes_out": 2_500_000, "bytes_in": 722},
                "host": "web1 (192.168.1.20)",
                "app": "ssh",
                "flow": flow,
            },
        )

        said = self.prompt(session, found)

        assert "What the programs said of the traffic" in said
        # The address of a device at home goes as a stand-in, as it does everywhere in the prompt.
        assert re.search(
            rf"Conversation: {ATTACKER} \(scanner\) \[remote\] -> HOST_\d+:22 \(ssh\) "
            r"\[NL, on a blacklist\] tcp ssh; 1 alerts of 1 kinds; "
            r"largest flow sent 2\.5 MB and got 722 B; lasted 61 s; "
            r"asked for scanner\.example\.net; reported by ntopng",
            said,
        )
        assert "Technique T1110 Brute (Credential Access): 1 alerts" in said
        assert "Groups and categories: Brute Force" in said
        assert re.search(r"Machine it was about: web1 \(HOST_\d+\)", said)
        assert "hostname named: scanner.example.net (1 alerts)" in said

    def test_the_traffic_is_told_in_stand_ins_where_the_level_hides_addresses(
        self, session: Session
    ) -> None:
        found = incident(session)
        signals(
            session,
            found,
            1,
            evidence={
                "facts": [],
                "tags": [],
                "mitre": [],
                "indicators": [],
                "flow": {"client": {"address": ATTACKER, "name": "scanner"}},
            },
        )

        said = self.prompt(session, found, Level.STRICT)

        assert "What the programs said of the traffic" in said
        assert "Conversation: " in said
        assert ATTACKER not in said

    def test_a_flow_with_no_volume_ends_or_names_is_told_by_what_is_known(
        self, session: Session
    ) -> None:
        found = incident(session)
        signals(session, found, 2, evidence=None, dst_port=None, protocol=None, signature="x")

        said = self.prompt(session, found)

        assert re.search(
            rf"Conversation: {ATTACKER} -> HOST_\d+; 2 alerts of 1 kinds; reported by", said
        )
        assert "largest flow" not in said
        assert "lasted" not in said
        assert "asked for" not in said

    def test_many_conversations_are_told_of_the_busiest_and_counted(self, session: Session) -> None:
        found = incident(session, signal_count=9)
        for port in range(9):
            signals(session, found, 1, dst_port=1000 + port, evidence=None)

        said = self.prompt(session, found)

        assert said.count("Conversation: ") == 6
        assert "... 3 more conversations ..." in said

    def test_data_sizes_are_told_in_the_unit_that_reads_best(self) -> None:
        assert [triage.size_of(count) for count in (0, 999, 1500, 2_000_000, 7_300_000_000)] == [
            "0 B",
            "999 B",
            "1.5 kB",
            "2.0 MB",
            "7.3 GB",
        ]
        assert triage.size_of(5 * 10**12) == "5000.0 GB"

    def test_the_question_names_what_it_is_and_what_is_about(self, session: Session) -> None:
        found = incident(session)

        asked = triage.question_for(session, found)

        assert asked.purpose == "triage"
        assert asked.about == f"incident {found.id}"
        assert asked.schema is triage.SCHEMA
        assert "probe: scanning" in asked.system
        assert asked.names == []

    def test_the_schema_allows_exactly_the_classes_and_verdicts_the_parser_does(self) -> None:
        properties: dict[str, Any] = dict(triage.SCHEMA["properties"])  # type: ignore[call-overload]
        assert tuple(properties["classification"]["enum"]) == CLASSES
        assert properties["verdict"]["enum"] == ["none", "not_suspicious", "low_priority", "threat"]
        assert sorted(triage.SCHEMA["required"]) == sorted(properties)  # type: ignore[arg-type]


class TestWhatTheAnswerMeans:
    def test_a_complete_answer_is_read(self) -> None:
        said = triage.parse(json.dumps(reading()))

        assert said == triage.Reading(
            classification="probe",
            confidence=91,
            headline="An internet scanner looked at one device",
            story="It tried a few ports. Nothing got in.",
            checks=["Look at the firewall rules for port 22", "Nothing else needed"],
            observations=["One address tried ports 22 and 80", "No data came back"],
            verdict="low_priority",
            verdict_reason="Routine background scanning.",
        )

    def test_observations_are_kept_to_their_number_and_length_and_may_be_left_out(self) -> None:
        many = [f"note {number}" for number in range(9)]
        said = triage.parse(json.dumps(reading(observations=[*many, 7, " ", "x" * 500])))

        assert said is not None
        assert said.observations == many[: triage.MAX_OBSERVATIONS]
        long = triage.parse(json.dumps(reading(observations=["x" * 500])))
        assert long is not None
        assert len(long.observations[0]) <= triage.MAX_OBSERVATION
        for left_out in ({"observations": "not a list"}, {"observations": None}):
            plain = triage.parse(json.dumps(reading(**left_out)))
            assert plain is not None
            assert plain.observations == []
        bare = reading()
        del bare["observations"]
        assert triage.parse(json.dumps(bare)) is not None

    def test_an_answer_in_a_code_fence_or_a_sentence_is_read(self) -> None:
        text = json.dumps(reading())

        assert triage.parse(f"```json\n{text}\n```") == triage.parse(text)
        assert triage.parse(f"Here is my reading: {text} Hope it helps.") == triage.parse(text)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "I think it is a scan.",
            "[1, 2]",
            '"probe"',
            "{ not json }",
            "```json\n{ not json }\n```",
            "5",
        ],
    )
    def test_what_is_not_an_object_is_not_a_reading(self, text: str) -> None:
        assert triage.parse(text) is None

    @pytest.mark.parametrize(
        "changes",
        [
            {"classification": "benign"},
            {"classification": 3},
            {"confidence": "high"},
            {"confidence": True},
            {"confidence": None},
            {"headline": 5},
            {"headline": "  "},
            {"story": None},
        ],
    )
    def test_an_answer_that_gets_a_field_wrong_is_no_reading(self, changes: dict[str, Any]) -> None:
        assert triage.parse(json.dumps(reading(**changes))) is None

    def test_a_field_that_is_missing_is_no_reading(self) -> None:
        said = reading()
        del said["story"]

        assert triage.parse(json.dumps(said)) is None

    def test_numbers_are_kept_to_their_range_and_words_to_their_length(self) -> None:
        low = triage.parse(json.dumps(reading(confidence=-5)))
        high = triage.parse(json.dumps(reading(confidence=250.4)))
        long = triage.parse(json.dumps(reading(headline="h" * 500, story="s" * 5000)))

        assert low is not None
        assert low.confidence == 0
        assert high is not None
        assert high.confidence == 100
        assert long is not None
        assert (len(long.headline), len(long.story)) == (160, 2000)

    def test_a_verdict_it_may_not_give_is_left_out(self) -> None:
        for given in ("none", "banned", 7, None):
            said = triage.parse(json.dumps(reading(verdict=given, verdict_reason=None)))
            assert said is not None
            assert said.verdict is None
            assert said.verdict_reason is None

    def test_at_most_a_few_checks_each_a_line_of_text(self) -> None:
        many = triage.parse(json.dumps(reading(checks=["a", "", 5, "b", "c", "d", "e", "f"])))
        none = triage.parse(json.dumps(reading(checks="look")))

        assert many is not None
        assert many.checks == ["a", "b", "c", "d"]
        assert none is not None
        assert none.checks == []

    def test_control_characters_in_words_are_spaces(self) -> None:
        said = triage.parse(json.dumps(reading(headline="two\nlines\x00here")))

        assert said is not None
        assert said.headline == "two lines here"


class TestKeepingWhatItSaid:
    def answer(self, text: str, *, ok: bool = True, truncated: bool = False) -> Answer:
        return Answer(
            ok=ok,
            text=text if ok else "",
            reason=None if ok else "Anthropic refused the key.",
            call_id=0,
            truncated=truncated,
        )

    def answered(self, session: Session, **changes: object) -> Answer:
        """An answer to a request that was kept, as the gateway gives it."""
        call = AiCall(
            purpose="triage",
            provider="anthropic",
            model="claude-haiku-5-5",
            level="balanced",
            ok=True,
            prompt="x",
        )
        session.add(call)
        session.flush()
        return Answer(
            ok=True,
            text=json.dumps(reading(**changes)),
            reason=None,
            call_id=call.id,
            provider=call.provider,
            model=call.model,
        )

    def test_nothing_asked_says_why(self, session: Session) -> None:
        found = incident(session)

        said = triage.keep(session, found, Unavailable("AI is turned off."), NOW)

        assert said == triage.NotRead("AI is turned off.")

    def test_a_provider_that_failed_says_so(self, session: Session) -> None:
        found = incident(session)

        said = triage.keep(session, found, self.answer("", ok=False), NOW)

        assert said == triage.NotRead("The AI provider didn't answer. Anthropic refused the key.")
        assert session.get(AiTriage, found.id) is None

    def test_an_answer_that_cannot_be_read_says_so_and_keeps_nothing(
        self, session: Session
    ) -> None:
        found = incident(session)

        plain = triage.keep(session, found, self.answer("It is a scan."), NOW)
        cut = triage.keep(session, found, self.answer('{"classif', truncated=True), NOW)

        assert isinstance(plain, triage.NotRead)
        assert plain.reason == "The AI answered, but not in a form AresGate could read. Try again."
        assert isinstance(cut, triage.NotRead)
        assert "cut short" in cut.reason
        assert session.get(AiTriage, found.id) is None

    def test_a_reading_is_kept_with_who_made_it(self, session: Session) -> None:
        found = incident(session)
        answer = self.answered(session)

        said = triage.keep(session, found, answer, NOW)

        assert isinstance(said, triage.Read)
        row = session.get(AiTriage, found.id)
        assert row is said.triage
        assert row is not None
        assert row.classification == "probe"
        assert row.confidence == 91
        assert row.checks == ["Look at the firewall rules for port 22", "Nothing else needed"]
        assert row.verdict == "low_priority"
        assert (row.provider, row.model) == ("anthropic", "claude-haiku-5-5")
        assert row.call_id == answer.call_id
        assert (row.read_at, row.signals_read) == (NOW, 3)

    def test_reading_it_again_replaces_the_reading(self, session: Session) -> None:
        found = incident(session)
        kept(session, found, classification="noise", headline="old", signals_read=1)

        said = triage.keep(
            session,
            found,
            self.answered(session, classification="attack", verdict="threat"),
            NOW,
        )

        assert isinstance(said, triage.Read)
        rows = session.scalars(select(AiTriage)).all()
        assert [(row.classification, row.verdict, row.signals_read) for row in rows] == [
            ("attack", "threat", 3)
        ]

    def test_the_numbers_of_the_classes_are_the_ones_the_database_allows(self) -> None:
        assert CLASSES == ("compromise", "attack", "probe", "noise", "unclear")
        assert USAGE_LEVELS == ("very_low", "low", "medium", "high", "maximum")
        assert set(triage.POLICIES) == set(USAGE_LEVELS)


class TestAskingNow:
    def test_the_ai_reads_it_and_the_real_names_come_back(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(reads_it())
        ready(session, settings)
        found = incident(session)
        signals(session, found)
        where = context(settings, Log(), server.url)

        async def from_a_thread() -> triage.Outcome:
            return await anyio.to_thread.run_sync(triage.ask_now, session, where, found, NOW)

        said = anyio.run(from_a_thread)

        assert isinstance(said, triage.Read)
        assert said.triage.story == f"{DEVICE} was scanned."
        assert DEVICE not in prompt_of(server.seen[0])
        call = session.scalars(select(AiCall)).one()
        assert call.about == f"incident {found.id}"
        assert "HOST_" in (call.answer or "")

    def test_nothing_is_asked_when_ai_is_off(self, session: Session, settings: Settings) -> None:
        found = incident(session)

        said = triage.ask_now(session, context(settings, Log()), found, NOW)

        assert isinstance(said, triage.NotRead)
        assert said.reason.startswith("AI is turned off.")
        assert session.scalars(select(AiCall)).all() == []

    def test_it_is_read_at_the_time_it_is_asked_for_if_no_time_is_given(
        self, session: Session, settings: Settings
    ) -> None:
        found = incident(session)

        said = triage.ask_now(session, context(settings, Log()), found)

        assert isinstance(said, triage.NotRead)


class TestWhichAreReadWithoutBeingAsked:
    def at_level(self, session: Session, settings: Settings, level: str = "medium") -> None:
        ready(session, settings)
        with_level(session, level)

    def planned(self, session: Session) -> list[int]:
        return triage.plan(session, NOW)

    def test_nothing_is_read_when_ai_is_off_or_has_no_provider(
        self, session: Session, settings: Settings
    ) -> None:
        found = incident(session, severity=4)
        assert self.planned(session) == []
        service.usage(session, NOW).enabled = True
        session.flush()
        assert self.planned(session) == []
        assert found.id

    @pytest.mark.parametrize(
        ("level", "severities"),
        [
            ("very_low", []),
            ("low", [3, 4]),
            ("medium", [2, 3, 4]),
            ("high", [1, 2, 3, 4]),
            ("maximum", [0, 1, 2, 3, 4]),
        ],
    )
    def test_the_level_decides_how_serious_an_incident_must_be(
        self, session: Session, settings: Settings, level: str, severities: list[int]
    ) -> None:
        self.at_level(session, settings, level)
        by_severity = {
            severity: incident(session, subject=f"s{severity}", severity=severity)
            for severity in range(5)
        }

        planned = self.planned(session)

        assert sorted(planned) == sorted(by_severity[severity].id for severity in severities)

    def test_the_most_serious_come_first(self, session: Session, settings: Settings) -> None:
        self.at_level(session, settings, "maximum")
        low = incident(session, subject="low", severity=1, confidence=90)
        high = incident(session, subject="high", severity=3, confidence=10)
        sure = incident(session, subject="sure", severity=3, confidence=70)
        recent = incident(session, subject="recent", severity=3, confidence=70, last_seen_at=NOW)

        assert self.planned(session) == [recent.id, sure.id, high.id, low.id]

    def test_an_incident_that_is_over_or_called_harmless_is_not_read(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings)
        incident(session, subject="a", status="resolved")
        incident(session, subject="b", status="dismissed")
        incident(session, subject="c", verdict="not_suspicious")
        incident(session, subject="d", verdict="low_priority")
        wanted = incident(session, subject="e", status="investigating")
        threat = incident(session, subject="f", verdict="threat")

        assert sorted(self.planned(session)) == sorted([wanted.id, threat.id])

    def test_one_that_was_read_is_not_read_again_at_the_lowest_level_until_asked(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        found = incident(session, severity=3, signal_count=100)
        kept(session, found, signals_read=1)

        assert self.planned(session) == []

    def test_one_that_has_grown_a_lot_is_read_again_but_not_before_a_pause(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        found = incident(session, signal_count=13)
        kept(session, found, signals_read=3)
        assert self.planned(session) == [found.id]

        asked_about(session, found, ok=True, minutes_ago=5)

        assert self.planned(session) == []

    def test_one_that_has_not_grown_enough_is_left(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        found = incident(session, signal_count=11)
        kept(session, found, signals_read=3)

        assert self.planned(session) == []

    def test_a_higher_level_reads_again_sooner(self, session: Session, settings: Settings) -> None:
        self.at_level(session, settings, "high")
        found = incident(session, signal_count=6)
        kept(session, found, signals_read=3)

        assert self.planned(session) == [found.id]

    def test_one_that_failed_lately_is_left_alone_for_a_while(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings)
        failed = incident(session, subject="failed")
        later = incident(session, subject="later")
        asked_about(session, failed, ok=False, minutes_ago=5)
        asked_about(session, later, ok=False, minutes_ago=20)

        assert self.planned(session) == [later.id]

    def test_only_so_many_are_read_in_an_hour_and_in_one_run(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        for n in range(8):
            incident(session, subject=f"i{n}", severity=3)

        assert len(self.planned(session)) == triage.PER_RUN

        for n in range(4):
            asked_about(
                session, incident(session, subject=f"old{n}", severity=0), ok=True, minutes_ago=30
            )

        assert len(self.planned(session)) == 2

        for n in range(2):
            asked_about(
                session, incident(session, subject=f"more{n}", severity=0), ok=True, minutes_ago=10
            )

        assert self.planned(session) == []

    def test_what_was_asked_more_than_an_hour_ago_does_not_count(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        found = incident(session, severity=3)
        for n in range(6):
            asked_about(
                session, incident(session, subject=f"old{n}", severity=0), ok=True, minutes_ago=90
            )

        assert self.planned(session) == [found.id]


class TestTheLoop:
    def reader(self, session: Session, settings: Settings, serve: Serve, handler: Handler) -> Any:
        server = serve(handler)
        ready(session, settings)
        with_level(session, "maximum")
        return context(settings, Log(), server.url), server

    def new_session(self, session: Session) -> Callable[[], Session]:
        return sessionmaker(bind=session.get_bind(), expire_on_commit=False)

    def test_it_reads_what_the_level_asks_for_and_keeps_it(
        self, session: Session, settings: Settings, serve: Serve, caplog: pytest.LogCaptureFixture
    ) -> None:
        where, server = self.reader(session, settings, serve, reads_it())
        first = incident(session, subject="first", severity=3)
        second = incident(session, subject="second", severity=1)
        signals(session, first)
        session.commit()

        with caplog.at_level(logging.INFO, "app.ai.run"):
            count = asyncio.run(run.read_once(self.new_session(session), where))

        assert count == 2
        assert len(server.seen) == 2
        session.expire_all()
        rows = session.scalars(select(AiTriage).order_by(AiTriage.incident_id)).all()
        assert [row.incident_id for row in rows] == [first.id, second.id]
        assert rows[0].story == f"{DEVICE} was scanned."
        assert "The AI read 2 incidents" in caplog.text

    def test_nothing_is_read_twice(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, reads_it())
        incident(session, severity=3)
        session.commit()
        new_session = self.new_session(session)

        assert asyncio.run(run.read_once(new_session, where)) == 1
        assert asyncio.run(run.read_once(new_session, where)) == 0
        assert len(server.seen) == 1

    def test_it_stops_at_a_provider_that_fails(
        self,
        session: Session,
        settings: Settings,
        serve: Serve,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        where, server = self.reader(session, settings, serve, anthropic_says("it is a scan"))
        for n in range(3):
            incident(session, subject=f"i{n}")
        session.commit()

        with caplog.at_level(logging.WARNING, "app.ai.run"):
            count = asyncio.run(run.read_once(self.new_session(session), where))

        assert count == 0
        assert len(server.seen) == 1
        assert "The AI didn't read incident" in caplog.text
        session.expire_all()
        assert session.scalars(select(AiTriage)).all() == []
        [call] = session.scalars(select(AiCall)).all()
        assert call.ok

    def test_it_goes_on_to_the_next_after_an_incident_that_has_gone(
        self,
        session: Session,
        settings: Settings,
        serve: Serve,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        where, _ = self.reader(session, settings, serve, reads_it())
        incident(session)
        session.commit()
        asked: list[int] = []

        async def gone(*_: object) -> None:
            asked.append(1)

        monkeypatch.setattr(run, "read_incident", gone)

        assert asyncio.run(run.read_once(self.new_session(session), where)) == 0
        assert asked == [1]

    def test_it_stops_when_the_ai_is_turned_off_between_planning_and_asking(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, reads_it())
        found = incident(session)
        session.commit()
        service.usage(session, NOW).enabled = False
        session.commit()

        said = asyncio.run(run.read_incident(self.new_session(session), where, found.id))

        assert isinstance(said, triage.NotRead)
        assert said.reason.startswith("AI is turned off.")
        assert server.seen == []

    def test_an_incident_that_has_gone_is_not_read(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, reads_it())

        said = asyncio.run(run.read_incident(self.new_session(session), where, 12345))

        assert said is None
        assert server.seen == []

    def test_an_incident_that_goes_while_it_is_read_is_not_kept(
        self, session: Session, settings: Settings, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        found = incident(session)
        session.commit()
        where, _ = self.reader(session, settings, serve, reads_it())
        real = gateway.send

        async def and_then_it_is_gone(prepared: gateway.Prepared, wanted: Any) -> gateway.Sent:
            sent = await real(prepared, wanted)
            with self.new_session(session)() as other:
                other.delete(other.get(Incident, found.id))
                other.commit()
            return sent

        monkeypatch.setattr(gateway, "send", and_then_it_is_gone)

        said = asyncio.run(run.read_incident(self.new_session(session), where, found.id))

        assert said is None
        session.expire_all()
        assert session.scalars(select(AiTriage)).all() == []
        assert len(session.scalars(select(AiCall)).all()) == 1

    def run_until_called(self, fake: FakeRead, times: int, *, enabled: bool = True) -> None:
        """Runs the loop, with its work swapped for the fake, until it has been called that many
        times (or for a moment, if it never will be), then cancels it."""

        async def loop() -> None:
            task = asyncio.create_task(
                run.run(
                    lambda: None,  # type: ignore[arg-type,return-value]
                    None,  # type: ignore[arg-type]
                    enabled=enabled,
                    interval=timedelta(milliseconds=1),
                )
            )
            for _ in range(50):
                if fake.calls >= times:
                    break
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.wait({task})

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(run, "read_once", fake)
            asyncio.run(loop())

    def test_the_loop_reads_again_and_again(self) -> None:
        fake = FakeRead()

        self.run_until_called(fake, 3)

        assert fake.calls >= 3

    def test_a_failed_run_is_logged_and_tried_again(self, caplog: pytest.LogCaptureFixture) -> None:
        fake = FakeRead(fail_first=True)

        with caplog.at_level(logging.ERROR):
            self.run_until_called(fake, 2)

        assert "Couldn't have the AI read the latest incidents" in caplog.text
        assert "the database isn't up yet" in caplog.text
        assert fake.calls >= 2

    def test_where_nothing_is_collected_nothing_is_read(self) -> None:
        fake = FakeRead()

        self.run_until_called(fake, 1, enabled=False)

        assert fake.calls == 0


class FakeRead:
    """Stands in for ``read_once``, counting its calls and failing the first one if told to."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    async def __call__(self, new_session: Callable[[], Session], where: object) -> int:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise ConnectionError("the database isn't up yet")
        return 0


class TestReputationInThePrompt:
    """What VirusTotal has said of the internet addresses an incident involves reaches the AI, and
    is redacted like the rest of what it is shown."""

    def prompt(self, session: Session, found: Incident, level: Level = Level.BALANCED) -> str:
        return triage.prompt_for(session, found, Redactor(session, level, NOW))

    def test_what_is_known_of_an_address_in_the_incident_is_given_to_the_ai(
        self, session: Session
    ) -> None:
        found = incident(session)
        report = virustotal.Report(
            malicious=3,
            suspicious=1,
            harmless=60,
            undetected=20,
            reputation=-12,
            analysed_at=NOW - timedelta(days=2),
            country="NL",
            owner="Example Hosting",
            asn=64500,
        )
        save_report(session, ip_address(ATTACKER), report)

        said = self.prompt(session, found)

        assert "What VirusTotal says of the internet addresses involved:" in said
        assert (
            f"- {ATTACKER}: 3 of 84 engines flag it as malicious and 1 as suspicious; owner "
            "Example Hosting, NL; community score -12; analysed "
            f"{report.analysed_at:%Y-%m-%d}"
        ) in said

    def test_an_owner_and_country_that_are_not_known_are_said_so(self, session: Session) -> None:
        found = incident(session)
        report = virustotal.Report(
            malicious=0,
            suspicious=0,
            harmless=70,
            undetected=5,
            reputation=0,
            analysed_at=NOW,
            country=None,
            owner=None,
            asn=None,
        )
        save_report(session, ip_address(ATTACKER), report)

        said = self.prompt(session, found)

        assert "owner unknown owner, unknown country; community score 0" in said

    def test_an_incident_without_any_report_has_no_reputation_lines(self, session: Session) -> None:
        found = incident(session)

        said = self.prompt(session, found)

        assert "What VirusTotal says" not in said

    def test_at_the_strictest_level_the_address_is_a_stand_in(self, session: Session) -> None:
        found = incident(session)
        report = virustotal.Report(
            malicious=1,
            suspicious=0,
            harmless=60,
            undetected=0,
            reputation=0,
            analysed_at=NOW,
            country="NL",
            owner="Example Hosting",
            asn=64500,
        )
        save_report(session, ip_address(ATTACKER), report)

        said = self.prompt(session, found, Level.STRICT)

        assert ATTACKER not in said
        assert "- EXT_" in said
