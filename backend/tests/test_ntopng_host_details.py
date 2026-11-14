import json
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng import host_details
from app.collectors.ntopng.host_details import PATH, HostDetails, parse
from app.config import Settings
from app.integrations import probes
from app.models import HostTrait
from e2e.stand_ins import Answer, answers, ntopng, sample_ntopng_extras, sample_ntopng_hosts
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve
from tests.test_ai_service import NOW


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert HostDetails.reads("ntopng", "api")
    assert not HostDetails.reads("opnsense", "api")
    assert collectors.find("ntopng-host-details") is not None
    assert HostDetails.interval == timedelta(minutes=30)
    assert HostDetails.timeout <= HostDetails.interval


class TestAHost:
    def test_it_has_what_ntopng_says_of_its_system_network_and_fingerprints(self) -> None:
        found = parse(
            "192.168.1.41",
            {
                "name": "laptop",
                "os": 1,
                "os_detail": "Windows 11",
                "asn": 64512,
                "asname": "Example ISP",
                "country": "CA",
                "ja4_fingerprint": {"t13d": {"app_name": "Chrome", "num_uses": 3}},
                "hassh_fingerprint": {
                    "abc": {"app_name": "ssh", "num_uses": 1, "is_malicious": True}
                },
                "tcp_fingerprint": "2:128",
            },
        )

        assert found is not None
        assert found.address == ip_address("192.168.1.41")
        assert (found.hostname, found.os_name) == ("laptop", "Windows 11")
        assert (found.asn, found.as_name, found.country) == (64512, "Example ISP", "CA")
        assert found.fingerprints == {
            "ja4": [{"value": "t13d", "app": "Chrome", "uses": 3, "malicious": False}],
            "hassh": [{"value": "abc", "app": "ssh", "uses": 1, "malicious": True}],
            "tcp": "2:128",
        }

    @pytest.mark.parametrize(
        ("number", "system"),
        [(1, "Windows"), (2, "macOS/iOS/iPadOS"), (3, "Android"), (4, "Linux"), (5, "FreeBSD")],
    )
    def test_a_system_it_has_only_a_number_for_is_named_by_it(
        self, number: int, system: str
    ) -> None:
        found = parse("192.168.1.41", {"os": number, "os_detail": ""})

        assert found is not None
        assert found.os_name == system

    def test_a_system_it_does_not_know_is_not_named(self) -> None:
        found = parse("192.168.1.41", {"os": 0})

        assert found is not None
        assert found.os_name is None

    def test_what_it_leaves_out_is_left_out(self) -> None:
        found = parse(
            "192.168.1.41", {"name": "192.168.1.41", "asn": 0, "asname": "", "country": ""}
        )

        assert found is not None
        assert (found.hostname, found.asn, found.as_name, found.country) == (None, None, None, None)
        assert found.fingerprints == {}

    def test_the_most_used_fingerprints_come_first_and_only_some_are_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(host_details, "FINGERPRINTS", 2)
        found = parse(
            "192.168.1.41",
            {
                "ja4_fingerprint": {
                    "a": {"num_uses": 1},
                    "b": {"num_uses": 30},
                    "c": {"num_uses": 5},
                    "d": "text",
                }
            },
        )

        assert found is not None
        assert [item["value"] for item in found.fingerprints["ja4"]] == ["b", "c"]

    def test_an_address_that_is_not_one_is_no_host(self) -> None:
        assert parse("not an address", {}) is None


class TestRunningAgainstNtopng:
    def test_it_keeps_what_ntopng_knows_of_each_busy_host(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=sample_ntopng_extras(NOW))).url,
        )

        collect(settings, engine, HostDetails())

        session.expire_all()
        rows = {str(row.address): row for row in session.scalars(select(HostTrait))}
        assert health(session).last_items == 2
        assert sorted(rows) == ["192.168.1.20", "192.168.1.41"]
        assert (rows["192.168.1.20"].hostname, rows["192.168.1.20"].os_name) == ("web1", "Linux")
        assert rows["192.168.1.20"].fingerprints["tcp"] == "2:128:1460:65535:1,3,1,1,4"
        assert (rows["192.168.1.41"].os_name, rows["192.168.1.41"].country) == ("Windows 11", "CA")
        flagged = rows["192.168.1.41"].fingerprints["ja4"]
        assert [item["malicious"] for item in flagged] == [False, True]

    def test_when_no_host_can_be_read_that_is_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras = {PATH: answers(None)}
        connect(
            session, settings, serve(ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=extras)).url
        )

        collect(settings, engine, HostDetails())

        assert health(session).last_error is not None

    def test_a_network_with_no_hosts_has_nothing_to_keep(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(session, settings, serve(ntopng(TOKEN, extras=sample_ntopng_extras(NOW))).url)

        collect(settings, engine, HostDetails())

        assert health(session).last_error is None
        assert health(session).last_items == 0

    def test_an_answer_that_is_not_an_object_is_not_taken_for_one(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        extras: dict[str, Any] = {PATH: answers(["x"])}
        connect(
            session, settings, serve(ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=extras)).url
        )

        collect(settings, engine, HostDetails())

        assert health(session).last_error == probes.unexpected("ntopng").message

    def test_a_host_whose_address_is_not_one_is_skipped(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        hosts = [{**sample_ntopng_hosts(NOW)[0], "ip": "web1.example"}]
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, hosts, extras={PATH: answers({"os": 4})})).url,
        )

        collect(settings, engine, HostDetails())

        assert health(session).last_items == 0
        assert session.scalars(select(HostTrait)).all() == []

    def test_a_host_ntopng_stops_listing_is_forgotten(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        connect(
            session,
            settings,
            serve(ntopng(TOKEN, sample_ntopng_hosts(NOW), extras=sample_ntopng_extras(NOW))).url,
        )
        collect(settings, engine, HostDetails())
        quiet = serve(lambda seen: Answer(body=json.dumps({"rc": 0, "rsp": {"data": []}})))
        connect(session, settings, quiet.url)

        collect(settings, engine, HostDetails())

        session.expire_all()
        assert session.scalars(select(HostTrait)).all() == []
