"""What was said on the wire: read from Suricata's record, then put together for an incident."""

import base64
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from app.incidents import evidence, occurrences, wire
from app.models import IncidentSignal

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

TLS: dict[str, Any] = {
    "alert_sid": 1,
    "alert": {"signature": "SURICATA TLS invalid certificate"},
    "tls": {
        "subject": "CN=cam.example.net",
        "issuerdn": "CN=cam.example.net",
        "serial": "00:AB",
        "fingerprint": "aa:bb",
        "version": "TLSv1.2",
        "sni": "cam.example.net",
        "notbefore": "2025-01-01T00:00:00",
        "notafter": "2035-01-01T00:00:00",
        "ja3": {"hash": "abc"},
        "ja3s": {"hash": "def"},
    },
}
HTTP: dict[str, Any] = {
    "alert_sid": 2,
    "alert": {"signature": "ET POLICY plain login"},
    "http": {
        "http_method": "POST",
        "hostname": "api.example.net",
        "url": "/login",
        "http_user_agent": "curl/8",
        "http_refer": "http://example.net/",
        "http_content_type": "application/json",
        "status": 200,
        "length": 120,
        "request_headers": [
            {"name": "Host", "value": "api.example.net"},
            {"name": "Authorization", "value": "Basic c2VjcmV0"},
            {"name": "Cookie", "value": "id=1"},
            {"name": "", "value": "ignored"},
            "not a header",
        ],
        "response_headers": [{"name": "Set-Cookie", "value": "s=2"}],
    },
}


def read(raw: dict[str, Any]) -> dict[str, Any]:
    found = evidence.extract("opnsense", raw)
    assert found is not None
    kept = found.get("wire")
    assert kept is not None
    return cast("dict[str, Any]", kept)


def signal(raw: dict[str, Any] | None, **changes: Any) -> IncidentSignal:
    row = IncidentSignal(
        source="opnsense",
        kind="alert",
        severity=2,
        summary="x",
        dst_address="192.0.2.10",
        dst_port=443,
        evidence=evidence.extract("opnsense", raw) if raw else None,
    )
    for key, value in changes.items():
        setattr(row, key, value)
    return row


def occurrence(
    raw: dict[str, Any] | None, count: int = 1, **changes: Any
) -> occurrences.Occurrence:
    return occurrences.Occurrence(
        first=signal(raw, **changes), count=count, last_at=NOW, duplicates=0
    )


class TestReadingTheWire:
    def test_a_certificate_is_kept_with_who_it_is_for_and_who_vouched_for_it(self) -> None:
        certificate = read(TLS)["certificate"]

        assert certificate == {
            "subject": "CN=cam.example.net",
            "issuer": "CN=cam.example.net",
            "serial": "00:AB",
            "fingerprint": "aa:bb",
            "version": "TLS 1.2",
            "sni": "cam.example.net",
            "not_before": "2025-01-01T00:00:00",
            "not_after": "2035-01-01T00:00:00",
            "ja3": "abc",
            "ja3s": "def",
            "self_signed": True,
        }

    def test_one_that_somebody_else_vouched_for_is_not_self_signed(self) -> None:
        raw = {**TLS, "tls": {**TLS["tls"], "issuerdn": "CN=Some CA, O=Example"}}

        assert "self_signed" not in read(raw)["certificate"]

    def test_the_commas_and_capitals_of_a_name_do_not_hide_that_it_is_self_signed(self) -> None:
        raw = {**TLS, "tls": {"subject": "C=US, CN=Cam", "issuerdn": "c=us,cn=cam"}}

        assert read(raw)["certificate"]["self_signed"] is True

    def test_a_handshake_with_only_a_name_asked_for_is_still_kept(self) -> None:
        raw = {"alert_sid": 1, "tls": {"sni": "cam.example.net", "version": "SSLv3"}}

        assert read(raw)["certificate"] == {"sni": "cam.example.net", "version": "SSLv3"}

    def test_a_handshake_that_says_nothing_of_who_is_left_out(self) -> None:
        raw = {"alert_sid": 1, "alert": {"signature": "x"}, "tls": {"version": "TLSv1.3"}}

        assert "wire" not in (evidence.extract("opnsense", raw) or {})

    def test_a_web_request_is_kept_and_the_value_of_a_secret_header_never_is(self) -> None:
        request = read(HTTP)["request"]

        assert request["method"] == "POST"
        assert (request["host"], request["url"]) == ("api.example.net", "/login")
        assert (request["status"], request["size"]) == (200, 120)
        assert request["request_headers"] == [
            ["Host", "api.example.net"],
            ["Authorization", evidence.HIDDEN],
            ["Cookie", evidence.HIDDEN],
        ]
        assert request["response_headers"] == [["Set-Cookie", evidence.HIDDEN]]
        assert "c2VjcmV0" not in str(request)

    def test_no_more_than_twenty_headers_are_kept(self) -> None:
        many = [{"name": f"X-{n}", "value": "v"} for n in range(40)]
        raw = {"alert_sid": 1, "http": {"hostname": "a", "request_headers": many}}

        assert len(read(raw)["request"]["request_headers"]) == evidence.MAX_HEADERS

    def test_a_name_that_was_looked_up_is_kept_with_what_came_back(self) -> None:
        raw = {
            "alert_sid": 1,
            "dns": {
                "rrname": "cam.example.net",
                "rrtype": "A",
                "rcode": "NOERROR",
                "answers": [{"rdata": f"192.0.2.{n}"} for n in range(9)] + ["bad", {"rdata": ""}],
            },
        }

        lookup = read(raw)["lookup"]

        assert (lookup["name"], lookup["type"], lookup["rcode"]) == (
            "cam.example.net",
            "A",
            "NOERROR",
        )
        assert lookup["answers"] == [f"192.0.2.{n}" for n in range(evidence.MAX_ANSWERS)]

    def test_a_lookup_with_no_answer_has_only_what_it_asked(self) -> None:
        raw = {"alert_sid": 1, "dns": {"rrname": "gone.example.net"}}

        assert read(raw)["lookup"] == {"name": "gone.example.net"}

    def test_a_lookup_with_no_name_is_left_out(self) -> None:
        raw = {"alert_sid": 1, "alert": {"signature": "x"}, "dns": {"rcode": "NOERROR"}}

        assert "wire" not in (evidence.extract("opnsense", raw) or {})

    def test_the_banners_of_ssh_are_kept_for_either_end(self) -> None:
        both = {"alert_sid": 1, "ssh": {"client": {"software_version": "OpenSSH_9"}}}
        server = {"alert_sid": 1, "ssh": {"server": {"software_version": "dropbear"}}}

        assert read(both)["ssh"] == {"client": "OpenSSH_9"}
        assert read(server)["ssh"] == {"server": "dropbear"}

    def test_an_alert_that_read_nothing_has_no_wire(self) -> None:
        raw = {"alert_sid": 1, "alert": {"signature": "x"}, "payload": "R0VU"}

        assert "wire" not in (evidence.extract("opnsense", raw) or {})


class TestPuttingItTogether:
    def test_an_incident_with_nothing_on_the_wire_has_an_empty_one(self) -> None:
        found = wire.of(
            [occurrence(None), occurrence({"alert_sid": 1, "alert": {"signature": "x"}})], NOW
        )

        assert found.empty
        assert found.notes == []
        assert wire.prompt_lines(found) == []

    def test_the_same_certificate_seen_by_many_alerts_is_one_with_how_many(self) -> None:
        found = wire.of([occurrence(TLS, 3), occurrence(TLS, 4, dst_port=8883)], NOW)

        [seen] = found.certificates
        assert seen.alerts == 7
        assert seen.server == "192.0.2.10:443"
        assert seen.expired is False
        assert not found.empty

    def test_the_most_often_seen_comes_first_and_only_so_many_are_kept(self) -> None:
        many = [
            occurrence({**TLS, "tls": {**TLS["tls"], "sni": f"h{n}.example.net"}}, n + 1)
            for n in range(wire.MAX_CERTIFICATES + 3)
        ]

        found = wire.of(many, NOW)

        assert len(found.certificates) == wire.MAX_CERTIFICATES
        assert found.certificates[0].alerts == wire.MAX_CERTIFICATES + 3

    def test_a_self_signed_certificate_comes_with_a_word_about_cameras_and_doorbells(self) -> None:
        [note] = wire.of([occurrence(TLS)], NOW).notes

        assert "cam.example.net is self-signed" in note
        assert "Cameras, doorbells" in note

    def test_one_that_ran_out_says_when(self) -> None:
        old = {**TLS, "tls": {**TLS["tls"], "issuerdn": "CN=CA", "notafter": "2020-01-01T00:00:00"}}

        found = wire.of([occurrence(old)], NOW)

        assert found.certificates[0].expired is True
        assert found.notes == [
            "The certificate for cam.example.net ran out on 2020-01-01T00:00:00."
        ]

    def test_a_zone_on_the_last_day_is_understood_and_nonsense_is_not_a_date(self) -> None:
        assert wire.expired("2020-01-01T00:00:00+00:00", NOW) is True
        assert wire.expired("2099-01-01T00:00:00Z", NOW) is False
        assert wire.expired("someday", NOW) is None
        assert wire.expired(None, NOW) is None

    @pytest.mark.parametrize("version", ["SSLv3", "TLSv1.0", "TLSv1.1"])
    def test_an_out_of_date_way_of_encrypting_is_said(self, version: str) -> None:
        weak = {**TLS, "tls": {**TLS["tls"], "issuerdn": "CN=CA", "version": version}}

        [note] = wire.of([occurrence(weak)], NOW).notes

        assert "out of date and weak" in note

    def test_a_login_sent_in_the_clear_is_said_without_its_value(self) -> None:
        found = wire.of([occurrence(HTTP)], NOW)

        [note] = found.notes
        assert "api.example.net as plain web traffic" in note
        assert "c2VjcmV0" not in str(found)

    def test_a_request_with_no_host_is_said_by_its_server(self) -> None:
        raw = {
            "alert_sid": 1,
            "http": {"url": "/", "request_headers": [{"name": "Cookie", "value": "a"}]},
        }

        [note] = wire.of([occurrence(raw)], NOW).notes

        assert "went to 192.0.2.10:443 as plain" in note

    def test_no_more_than_five_notes_and_none_twice(self) -> None:
        many = [
            occurrence({**TLS, "tls": {**TLS["tls"], "sni": f"h{n}.example.net"}}) for n in range(8)
        ]

        notes = wire.of([*many, *many], NOW).notes

        assert len(notes) == wire.MAX_NOTES
        assert len(set(notes)) == len(notes)

    def test_requests_lookups_and_banners_are_each_folded_and_counted(self) -> None:
        lookup = {"alert_sid": 1, "dns": {"rrname": "a.example.net", "rrtype": "A"}}
        ssh = {"alert_sid": 1, "ssh": {"client": {"software_version": "OpenSSH_9"}}}
        found = wire.of(
            [
                occurrence(HTTP, 2),
                occurrence(HTTP, 3),
                occurrence(lookup, 4),
                occurrence(lookup, 1),
                occurrence(ssh, 5, dst_port=22),
                occurrence(ssh, 1, dst_port=22),
            ],
            NOW,
        )

        assert [each.alerts for each in found.requests] == [5]
        assert [each.alerts for each in found.lookups] == [5]
        assert [each.alerts for each in found.banners] == [6]
        assert found.banners[0].server == "192.0.2.10:22"

    def test_a_server_with_no_port_is_told_by_its_address_and_none_by_nothing(self) -> None:
        assert wire.server_of(occurrence(TLS, dst_port=None)) == "192.0.2.10"
        assert wire.server_of(occurrence(TLS, dst_address=None)) is None

    def test_the_packet_that_set_an_alert_off_is_kept_as_dump_and_text(self) -> None:
        raw = {
            "alert_sid": 1,
            "alert": {"signature": "x"},
            "payload": base64.b64encode(b"GET / HTTP/1.1").decode(),
            "payload_printable": "GET / HTTP/1.1",
        }

        found = wire.of([occurrence(raw), occurrence(raw)], NOW)

        assert found.payload == "GET / HTTP/1.1"
        assert found.dump[0][0] == "0000"
        assert not found.empty

    def test_what_a_second_program_saw_is_counted_too(self) -> None:
        agreed = occurrences.Confirmation(
            source="wazuh",
            signature=None,
            severity=2,
            count=2,
            first_at=NOW,
            last_at=NOW,
            evidence=evidence.extract("opnsense", HTTP),
        )
        first = occurrence(None)
        both = occurrences.Occurrence(
            first=first.first, count=1, last_at=NOW, duplicates=1, confirmations=(agreed,)
        )

        [seen] = wire.of([both], NOW).requests

        assert seen.alerts == 2


class TestWhatTheAiIsTold:
    def test_each_thing_is_a_line_and_so_is_what_stands_out(self) -> None:
        lookup = {
            "alert_sid": 1,
            "dns": {"rrname": "a.example.net", "answers": [{"rdata": "192.0.2.1"}]},
        }
        gone = {"alert_sid": 1, "dns": {"rrname": "gone.example.net"}}
        ssh = {"alert_sid": 1, "ssh": {"client": {"software_version": "OpenSSH_9"}}}
        text = {
            "alert_sid": 1,
            "alert": {"signature": "x"},
            "payload_printable": "GET /admin",
        }
        found = wire.of(
            [
                occurrence(TLS, 2),
                occurrence(HTTP),
                occurrence(lookup),
                occurrence(gone),
                occurrence(ssh),
                occurrence(text),
            ],
            NOW,
        )

        lines = wire.prompt_lines(found)

        assert lines[0] == (
            "Certificate shown for cam.example.net by 192.0.2.10:443; self-signed; over TLS 1.2; "
            "good until 2035-01-01T00:00:00; 2 alerts"
        )
        assert any(
            line.startswith(
                "Plain web request: POST api.example.net/login; user agent curl/8; answer 200"
            )
            for line in lines
        )
        assert "Name looked up: a.example.net -> 192.0.2.1; 1 alerts" in lines
        assert "Name looked up: gone.example.net -> no answer; 1 alerts" in lines
        assert "ssh banners: client OpenSSH_9" in lines
        assert "Start of the packet that set an alert off, as text: GET /admin" in lines
        assert sum(line.startswith("Note: ") for line in lines) == 2

    def test_a_certificate_that_ran_out_and_a_request_with_nothing_but_the_server(self) -> None:
        old = {
            **TLS,
            "tls": {"issuerdn": "CN=CA", "subject": "CN=a", "notafter": "2020-01-01T00:00:00"},
        }
        bare = {"alert_sid": 1, "http": {"status": 404}}

        lines = wire.prompt_lines(wire.of([occurrence(old), occurrence(bare)], NOW))

        assert (
            "Certificate shown for CN=a by 192.0.2.10:443; issued by CN=CA; "
            "ran out 2020-01-01T00:00:00; 1 alerts" in lines
        )
        assert "Plain web request: request 192.0.2.10:443; answer 404; 1 alerts" in lines

    def test_a_certificate_with_no_version_or_dates_is_told_by_who_vouched_for_it(self) -> None:
        bare = {"alert_sid": 1, "tls": {"issuerdn": "CN=CA"}}

        [line] = wire.prompt_lines(wire.of([occurrence(bare)], NOW))

        assert line == (
            "Certificate shown for a server by 192.0.2.10:443; issued by CN=CA; 1 alerts"
        )

    def test_a_certificate_with_nothing_to_call_it_by_is_a_server(self) -> None:
        assert wire.called({"issuer": "CN=CA"}) == "a server"
