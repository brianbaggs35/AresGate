import asyncio
import json
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any, cast

import pytest

from app import __version__
from app.alerts import discord
from app.alerts.discord import InvalidWebhook, Sent
from app.integrations import netguard
from app.integrations.client import Call
from e2e.stand_ins import Seen
from e2e.stand_ins import discord as discord_stand_in
from tests.stubs import Answer, Serve

ID = "1234567890123456789"
TOKEN = "Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x"
ADDRESS = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def embed_of(payload: dict[str, object]) -> dict[str, Any]:
    """The one embed of a message."""
    [embed] = cast("list[dict[str, Any]]", payload["embeds"])
    return embed


class Log:
    """What the client wrote to the API log."""

    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def post(
    server_url: str | None,
    log: Log,
    *,
    policy: netguard.AddressPolicy = netguard.PUBLIC_INTERNET_AND_LOOPBACK,
    payload: dict[str, object] | None = None,
) -> Sent:
    return asyncio.run(
        discord.send(
            discord.parse(ADDRESS),
            payload or discord.check_message("Security", NOW),
            connection="destination-1",
            recorder=log,
            policy=policy,
            origin=server_url,
        )
    )


class TestTheAddress:
    @pytest.mark.parametrize(
        "address",
        [
            ADDRESS,
            ADDRESS + "/",
            f"  {ADDRESS}  ",
            ADDRESS.replace("discord.com", "discordapp.com"),
            ADDRESS.replace("discord.com", "DISCORD.com"),
            ADDRESS.replace("/api/", "/api/v10/"),
            ADDRESS.replace("discord.com", "discord.com:443"),
        ],
    )
    def test_the_address_discord_gives_is_taken(self, address: str) -> None:
        webhook = discord.parse(address)

        assert (webhook.id, webhook.token) == (ID, TOKEN)
        assert webhook.host in discord.HOSTS

    def test_it_is_put_together_the_way_it_was_given(self) -> None:
        assert discord.parse(ADDRESS).url == ADDRESS
        assert discord.parse(ADDRESS.replace("/api/", "/api/v10/")).path == (
            f"/api/v10/webhooks/{ID}/{TOKEN}"
        )

    def test_its_hint_is_the_end_of_the_number_and_none_of_the_token(self) -> None:
        webhook = discord.parse(ADDRESS)

        assert webhook.hint == "…6789"
        assert TOKEN[:6] not in webhook.hint

    @pytest.mark.parametrize(
        ("address", "says"),
        [
            ("", "Paste the webhook address"),
            ("   ", "Paste the webhook address"),
            ("x" * 401, "too long"),
            ("http://[::1", "isn't a web address"),
            (ADDRESS.replace("https", "http"), "starts with https://"),
            ("discord.com/api/webhooks/1/2", "starts with https://"),
            ("https://example.com/api/webhooks/1234567890123456789/" + TOKEN, "isn't a Discord"),
            (ADDRESS.replace("discord.com", "ptb.discord.com"), "isn't a Discord"),
            (ADDRESS.replace("discord.com", "discord.com.evil.test"), "isn't a Discord"),
            (ADDRESS.replace("discord.com", "evildiscord.com"), "isn't a Discord"),
            (ADDRESS.replace("discord.com", "192.168.1.10"), "isn't a Discord"),
            (ADDRESS.replace("discord.com", "[::1]"), "isn't a Discord"),
            (ADDRESS.replace("https://", "https://discord.com@evil.test/x#"), "isn't a Discord"),
            (ADDRESS.replace("https://", "https://user:pw@"), "exactly as Discord shows"),
            (ADDRESS.replace("discord.com", "discord.com:8443"), "exactly as Discord shows"),
            (ADDRESS + "?wait=true", "exactly as Discord shows"),
            (ADDRESS + "#top", "exactly as Discord shows"),
            (f"https://discord.com/api/webhooks/{ID}", "doesn't look like a webhook"),
            (f"https://discord.com/api/webhooks/{ID}/{TOKEN}/github", "doesn't look like"),
            (f"https://discord.com/api/webhooks/abc/{TOKEN}", "doesn't look like"),
            (f"https://discord.com/api/webhooks/{ID}/short", "doesn't look like"),
            (f"https://discord.com/api/webhooks/{ID}/{'a' * 161}", "doesn't look like"),
            (f"https://discord.com/api/webhooks/{ID}/tok%20en{'a' * 20}", "doesn't look like"),
            (f"https://discord.com/api/channels/{ID}/{TOKEN}", "doesn't look like"),
            (f"https://discord.com/webhooks/{ID}/{TOKEN}", "doesn't look like"),
            (f"https://discord.com/api/vX/webhooks/{ID}/{TOKEN}", "doesn't look like"),
            (f"https://discord.com/api/v10/v9/webhooks/{ID}/{TOKEN}", "doesn't look like"),
        ],
    )
    def test_what_is_not_a_discord_webhook_is_refused_in_words(
        self, address: str, says: str
    ) -> None:
        with pytest.raises(InvalidWebhook, match=says) as refused:
            discord.parse(address)

        assert TOKEN not in str(refused.value)


class TestTheMessage:
    def test_a_message_is_one_embed_that_pings_no_one(self) -> None:
        sent = discord.message(
            title="Title",
            description="Words",
            color=discord.RED,
            footer="Foot",
            link="https://aresgate.example/incidents/4",
            at=NOW,
        )

        assert sent == {
            "username": "AresGate",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": "Title",
                    "description": "Words",
                    "color": discord.RED,
                    "url": "https://aresgate.example/incidents/4",
                    "footer": {"text": "Foot"},
                    "timestamp": "2026-11-01T12:00:00+00:00",
                }
            ],
        }

    def test_what_is_left_out_is_left_out(self) -> None:
        embed = embed_of(discord.message(title="T", description="D"))

        assert set(embed) == {"title", "description", "color"}

    def test_words_over_discords_limits_are_cut(self) -> None:
        embed = embed_of(
            discord.message(title="t" * 400, description="d" * 5000, footer="f" * 3000)
        )

        assert len(embed["title"]) == discord.MAX_TITLE
        assert embed["title"].endswith("…")
        assert len(embed["description"]) == discord.MAX_DESCRIPTION
        assert len(embed["footer"]["text"]) == 2048

    def test_fields_are_added_within_discords_limits(self) -> None:
        many = [
            (f"Name {n}", "v" * 2000 if n == 0 else f"Value {n}", n % 2 == 0) for n in range(30)
        ]

        embed = embed_of(discord.message(title="T", description="D", fields=many))

        assert len(embed["fields"]) == discord.MAX_FIELDS
        assert embed["fields"][0]["name"] == "Name 0"
        assert len(embed["fields"][0]["value"]) == discord.MAX_FIELD_VALUE
        assert embed["fields"][0]["value"].endswith("…")
        assert embed["fields"][1] == {"name": "Name 1", "value": "Value 1", "inline": False}
        assert embed["fields"][2]["inline"] is True

    def test_the_test_message_names_the_destination_and_says_nothing_is_wrong(self) -> None:
        embed = embed_of(discord.check_message("Security", NOW))

        assert "Security" in embed["description"]
        assert "Nothing is wrong" in embed["description"]
        assert embed["footer"] == {"text": "AresGate · test message"}


class TestWhatDiscordSaid:
    @pytest.mark.parametrize("status", [200, 204])
    def test_it_went_through(self, status: int) -> None:
        assert discord.judge(status, None) == Sent(True, status)

    def test_a_limit_says_how_long_to_wait(self) -> None:
        sent = discord.judge(429, {"message": "You are being rate limited.", "retry_after": 1.5})

        assert (sent.ok, sent.retry, sent.retry_after, sent.gone) == (False, True, 1.5, False)
        assert sent.problem == (
            "Discord is limiting how fast messages can be sent here (HTTP 429). Wait for 1.5 "
            "seconds."
        )

    @pytest.mark.parametrize("body", [None, {}, {"retry_after": "soon"}, {"retry_after": -1}, []])
    def test_a_limit_without_a_time_is_a_moment(self, body: object) -> None:
        sent = discord.judge(429, body)

        assert (sent.retry, sent.retry_after) == (True, None)
        assert sent.problem is not None
        assert sent.problem.endswith("Wait for a moment.")

    def test_a_limit_with_no_time_in_the_body_reads_it_from_the_header(self) -> None:
        sent = discord.judge(429, None, {"retry-after": "4"})

        assert (sent.retry, sent.retry_after) == (True, 4.0)

    @pytest.mark.parametrize("value", ["soon", "-1", "99999", ""])
    def test_a_time_in_the_header_that_makes_no_sense_is_not_believed(self, value: str) -> None:
        assert discord.judge(429, None, {"retry-after": value}).retry_after is None

    def test_the_body_is_believed_before_the_header(self) -> None:
        sent = discord.judge(429, {"retry_after": 1.5}, {"retry-after": "4"})

        assert sent.retry_after == 1.5

    def test_a_message_that_used_the_last_of_the_allowance_says_how_long_to_wait(self) -> None:
        sent = discord.judge(
            204, None, {"x-ratelimit-remaining": "0", "x-ratelimit-reset-after": "1.5"}
        )

        assert (sent.ok, sent.pause) == (True, 1.5)

    @pytest.mark.parametrize(
        "headers",
        [
            {"x-ratelimit-remaining": "3", "x-ratelimit-reset-after": "1.5"},
            {"x-ratelimit-remaining": "0"},
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset-after": "nan?"},
            {},
        ],
    )
    def test_otherwise_there_is_nothing_to_wait_for(self, headers: dict[str, str]) -> None:
        assert discord.judge(204, None, headers).pause is None

    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_a_webhook_that_is_refused_is_gone(self, status: int) -> None:
        sent = discord.judge(status, {"message": "Unknown Webhook", "code": 10015})

        assert (sent.ok, sent.gone, sent.retry) == (False, True, False)
        assert sent.problem is not None
        assert f"HTTP {status}" in sent.problem
        assert "replace the address" in sent.problem

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_a_fault_of_discords_can_be_tried_again(self, status: int) -> None:
        sent = discord.judge(status, None)

        assert (sent.ok, sent.retry, sent.gone) == (False, True, False)

    @pytest.mark.parametrize("status", [400, 413, 418])
    def test_another_refusal_is_ours_to_fix(self, status: int) -> None:
        sent = discord.judge(status, {"message": "Invalid Form Body", "code": 50035})

        assert (sent.ok, sent.retry, sent.gone) == (False, False, False)
        assert sent.problem is not None
        assert "report it" in sent.problem
        assert "Invalid Form Body" not in sent.problem


class TestSending:
    def stand_in(self, serve: Serve, known: str = f"{ID}/{TOKEN}") -> Any:
        return serve(discord_stand_in(known))

    def test_a_message_is_posted_to_the_webhook_and_is_taken(self, serve: Serve) -> None:
        server = self.stand_in(serve)

        sent = post(server.url, Log())

        assert sent == Sent(True, 204)
        [seen] = server.seen
        assert (seen.method, seen.path) == ("POST", f"/api/webhooks/{ID}/{TOKEN}")
        assert (
            seen.headers["user-agent"]
            == f"DiscordBot (https://github.com/brianbaggs35/AresGate, {__version__})"
        )
        assert seen.headers["content-type"] == "application/json"
        assert json.loads(seen.body)["allowed_mentions"] == {"parse": []}

    def test_the_log_has_the_request_without_the_address(self, serve: Serve) -> None:
        server = self.stand_in(serve)
        log = Log()

        post(server.url, log)

        [call] = log.calls
        assert (call.integration, call.connection, call.method, call.status_code) == (
            "discord",
            "destination-1",
            "POST",
            204,
        )
        assert call.path == discord.LOGGED_PATH
        assert TOKEN not in repr(call)
        assert ID not in repr(call)

    def test_a_webhook_discord_does_not_know_is_gone(self, serve: Serve) -> None:
        server = self.stand_in(serve, known="1/other")
        log = Log()

        sent = post(server.url, log)

        assert (sent.ok, sent.status, sent.gone, sent.retry) == (False, 404, True, False)
        assert log.calls[0].error == "Not Found"
        assert TOKEN not in repr(log.calls)

    def test_a_limit_is_read_from_the_answer(self, serve: Serve) -> None:
        server = serve(
            lambda seen: Answer(
                429, json.dumps({"message": "slow", "retry_after": 2.25, "global": False})
            )
        )

        sent = post(server.url, Log())

        assert (sent.status, sent.retry, sent.retry_after) == (429, True, 2.25)

    def test_nobody_answering_is_something_to_try_again(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(drop=True))

        sent = post(server.url, Log())

        assert (sent.ok, sent.status, sent.retry) == (False, None, True)
        assert sent.problem

    def test_a_redirect_is_not_followed(self, serve: Serve) -> None:
        elsewhere = serve(lambda seen: Answer(204))
        server = serve(lambda seen: Answer(307, headers={"Location": elsewhere.url + "/x"}))
        log = Log()

        sent = post(server.url, log)

        assert sent.ok is False
        assert elsewhere.seen == []
        assert log.calls[0].error == "Redirected to another address, which AresGate doesn't follow."

    def test_the_token_is_kept_out_of_what_goes_wrong(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(drop=True))
        log = Log()

        sent = post(server.url, log)

        assert TOKEN not in (sent.problem or "")
        assert TOKEN not in repr(log.calls)

    def test_the_network_guard_keeps_it_off_the_home_network(self, serve: Serve) -> None:
        server = self.stand_in(serve)

        sent = post(server.url, Log(), policy=netguard.PUBLIC_INTERNET)

        assert sent.ok is False
        assert server.seen == []
        assert sent.problem is not None
        assert "won't connect" in sent.problem

    def test_discord_itself_is_where_it_goes_without_the_harness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[str] = []

        async def lookup(host: str, port: int) -> list[netguard.IPAddress]:
            asked.append(f"{host}:{port}")
            # A name made to lead to the home network, as an attack would.
            return [ip_address("192.168.1.10")]

        monkeypatch.setattr(netguard, "lookup_async", lookup)

        sent = post(None, Log(), policy=netguard.PUBLIC_INTERNET)

        assert asked == ["discord.com:443"]
        assert sent.ok is False
        assert sent.problem == (
            "discord.com is at 192.168.1.10, which isn't an address on the internet, so "
            "AresGate won't connect to it. AI providers are on the internet, not on your own "
            "network."
        )


class TestWhatDiscordCalledAMessage:
    def test_a_message_that_was_waited_for_has_the_name_discord_gave_it(self) -> None:
        sent = discord.judge(200, {"id": "1100000000000000001", "type": 0})

        assert sent == Sent(True, 200, message_id="1100000000000000001")

    @pytest.mark.parametrize(
        "body", [None, "text", {}, {"id": 5}, {"id": "abc"}, {"id": "1" * 40}, [{"id": "1"}]]
    )
    def test_a_name_that_is_not_one_is_not_kept(self, body: object) -> None:
        assert discord.judge(200, body).message_id is None
        assert discord.judge(204, None).message_id is None

    def test_an_edit_of_a_message_that_was_deleted_is_not_the_webhooks_fault(self) -> None:
        sent = discord.judge_edit(404, {"message": "Unknown Message", "code": 10008})

        assert (sent.ok, sent.missing, sent.gone, sent.retry) == (False, True, False, False)
        assert sent.problem == "The message was deleted in Discord, so there was nothing to update."

    @pytest.mark.parametrize(
        "body", [{"message": "Unknown Webhook", "code": 10015}, {"code": True}, {"code": "x"}, None]
    )
    def test_any_other_404_is_a_webhook_that_is_gone(self, body: object) -> None:
        sent = discord.judge_edit(404, body)

        assert (sent.missing, sent.gone) == (False, True)

    def test_an_edit_that_worked_is_taken(self) -> None:
        assert discord.judge_edit(200, {"id": "1100000000000000001"}).ok


class TestWaitingForTheMessageAndEditingIt:
    def stand_in(self, serve: Serve) -> Any:
        return serve(discord_stand_in(f"{ID}/{TOKEN}"))

    def wait_for(self, server: Any, log: Log | None = None) -> Sent:
        return asyncio.run(
            discord.send(
                discord.parse(ADDRESS),
                discord.check_message("Security", NOW),
                connection="destination-1",
                recorder=log or Log(),
                policy=netguard.PUBLIC_INTERNET_AND_LOOPBACK,
                origin=server.url,
                wait=True,
            )
        )

    def edit(self, server: Any, message_id: str, log: Log | None = None) -> Sent:
        return asyncio.run(
            discord.edit(
                discord.parse(ADDRESS),
                message_id,
                discord.check_message("Changed", NOW),
                connection="destination-1",
                recorder=log or Log(),
                policy=netguard.PUBLIC_INTERNET_AND_LOOPBACK,
                origin=server.url,
            )
        )

    def test_it_asks_discord_to_name_the_message(self, serve: Serve) -> None:
        server = self.stand_in(serve)

        sent = self.wait_for(server)

        assert sent.ok
        assert sent.message_id == "1100000000000000001"
        assert server.seen[0].target == f"/api/webhooks/{ID}/{TOKEN}?wait=true"

    def test_a_message_is_edited_where_it_was_made(self, serve: Serve) -> None:
        server = self.stand_in(serve)
        made = self.wait_for(server)
        log = Log()

        sent = self.edit(server, made.message_id or "", log)

        assert sent.ok
        patch = server.seen[1]
        assert (patch.method, patch.path) == (
            "PATCH",
            f"/api/webhooks/{ID}/{TOKEN}/messages/{made.message_id}",
        )
        assert json.loads(patch.body)["embeds"][0]["title"] == "AresGate can reach this channel"
        assert [call.path for call in log.calls] == [discord.LOGGED_PATH]
        assert TOKEN not in repr(log.calls)

    def test_a_message_that_was_never_made_or_was_deleted_is_missing(self, serve: Serve) -> None:
        server = self.stand_in(serve)

        sent = self.edit(server, "1100000000000000099")

        assert (sent.ok, sent.missing, sent.gone) == (False, True, False)

    def test_a_name_that_is_not_one_is_never_put_in_an_address(self, serve: Serve) -> None:
        server = self.stand_in(serve)

        sent = self.edit(server, "../../x")

        assert (sent.ok, sent.status) == (False, None)
        assert server.seen == []

    def test_editing_through_a_webhook_that_is_gone_says_so(self, serve: Serve) -> None:
        server = serve(discord_stand_in("1/other"))

        sent = self.edit(server, "1100000000000000001")

        assert (sent.ok, sent.gone, sent.missing) == (False, True, False)


class TestTheDiscordStandIn:
    def ask(self, method: str, path: str) -> Answer:
        handle = discord_stand_in(f"{ID}/{TOKEN}")
        agent = {"user-agent": "DiscordBot (https://example.test, 1)"}
        return handle(Seen(method, path, agent, b'{"content": "x"}'))

    def test_only_a_post_or_a_patch_to_a_webhook_is_answered(self) -> None:
        assert self.ask("GET", f"/api/webhooks/{ID}/{TOKEN}").status == 404
        assert self.ask("POST", "/api/users").status == 404

    def test_an_edit_needs_a_message_path_and_a_post_does_not_have_one(self) -> None:
        assert self.ask("PATCH", f"/api/webhooks/{ID}/{TOKEN}").status == 404
        assert self.ask("POST", f"/api/webhooks/{ID}/{TOKEN}/messages/1").status == 404
