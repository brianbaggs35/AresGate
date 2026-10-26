import asyncio
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest

from app.collectors.opnsense.firewall_log import parse
from app.collectors.opnsense.suricata_alerts import parse as parse_alerts
from app.events.event import Severity
from app.integrations import netguard, registry
from e2e import stand_ins
from e2e.stand_ins import Answer, Handler, Seen, StandIns, StubServer


def seen(path: str, **headers: str) -> Seen:
    return Seen("GET", path, headers, b"")


def basic(user: str, password: str) -> str:
    return stand_ins._basic(user, password)  # pyright: ignore[reportPrivateUsage]


def body(answer: Answer) -> Any:
    """What an answer says, as JSON."""
    return json.loads(answer.body)


class TestNtopng:
    handler = staticmethod(stand_ins.ntopng("right-token"))

    def test_it_lists_its_interfaces_for_the_token(self) -> None:
        answer = self.handler(
            seen("/lua/rest/v2/get/ntopng/interfaces.lua", authorization="Token right-token")
        )

        assert answer.status == 200
        assert body(answer) == {
            "rc": 0,
            "rc_str": "OK",
            "rc_str_hr": "Success",
            "rsp": [{"ifid": 0, "ifname": "eth0"}],
        }

    @pytest.mark.parametrize("authorization", ["Token wrong", "Bearer right-token", None])
    def test_it_sends_a_login_it_refuses_to_its_login_page(self, authorization: str | None) -> None:
        headers = {} if authorization is None else {"authorization": authorization}

        answer = self.handler(seen("/lua/rest/v2/get/ntopng/interfaces.lua", **headers))

        assert (answer.status, answer.headers) == (302, {"Location": "/lua/login.lua"})

    def test_it_sends_anything_else_to_the_login_page_too(self) -> None:
        answer = self.handler(seen("/other", authorization="Token right-token"))

        assert answer.status == 302


class TestNtopngReadings:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    login: ClassVar[dict[str, str]] = {"authorization": "Token right-token"}

    def handler(self, **kinds: Any) -> Handler:
        return stand_ins.ntopng("right-token", **kinds)

    def test_the_hosts_of_the_local_network_are_the_ones_asked_for(self) -> None:
        handler = self.handler(hosts=stand_ins.sample_ntopng_hosts(self.now))

        local = handler(seen("/lua/rest/v2/get/host/active.lua?ifid=0&mode=local", **self.login))
        every = handler(seen("/lua/rest/v2/get/host/active.lua?ifid=0", **self.login))

        assert [item["ip"] for item in body(local)["rsp"]["data"]] == [
            "192.168.1.20",
            "192.168.1.41",
            "192.168.2.15",
        ]
        assert len(body(every)["rsp"]["data"]) == 4
        assert (body(local)["rc"], body(local)["rc_str"]) == (0, "OK")

    def test_the_interface_data_is_given_for_the_interface_it_has(self) -> None:
        handler = self.handler(interface=stand_ins.sample_ntopng_interface())

        answer = handler(seen("/lua/rest/v2/get/interface/data.lua?ifid=0", **self.login))

        assert body(answer)["rsp"]["ifname"] == "eth0"

    @pytest.mark.parametrize(
        "path",
        [
            "/lua/rest/v2/get/host/active.lua",
            "/lua/rest/v2/get/interface/data.lua",
            "/lua/rest/v2/get/flow/alert/list.lua",
            "/lua/rest/v2/get/host/alert/list.lua",
        ],
    )
    def test_an_interface_it_does_not_have_is_an_error_in_the_answer(self, path: str) -> None:
        answer = self.handler()(seen(f"{path}?ifid=4", **self.login))
        missing = self.handler()(seen(path, **self.login))

        assert answer.status == 200
        assert body(answer) == {
            "rc": -2,
            "rc_str": "INVALID_INTERFACE",
            "rc_str_hr": "INVALID_INTERFACE",
            "rsp": {},
        }
        assert body(missing)["rc"] == -2

    def test_the_alerts_between_the_times_asked_for_come_newest_first_up_to_the_length(
        self,
    ) -> None:
        handler = self.handler(flow_alerts=stand_ins.sample_ntopng_flow_alerts(self.now))
        begin = int((self.now - timedelta(minutes=30)).timestamp())
        end = int(self.now.timestamp())

        answer = handler(
            seen(
                f"/lua/rest/v2/get/flow/alert/list.lua?ifid=0&epoch_begin={begin}&epoch_end={end}"
                "&length=1&sort=tstamp&order=desc",
                **self.login,
            )
        )
        all_of_them = handler(
            seen(
                f"/lua/rest/v2/get/flow/alert/list.lua?ifid=0&epoch_begin=0&epoch_end={end}",
                **self.login,
            )
        )

        assert [item["row_id"] for item in body(answer)["rsp"]["records"]] == ["101"]
        assert (body(answer)["recordsTotal"], body(answer)["recordsFiltered"]) == (2, 2)
        assert [item["row_id"] for item in body(all_of_them)["rsp"]["records"]] == [
            "101",
            "100",
            "99",
        ]

    def test_the_host_alerts_are_listed_apart_from_the_flow_alerts(self) -> None:
        handler = self.handler(
            flow_alerts=stand_ins.sample_ntopng_flow_alerts(self.now),
            host_alerts=stand_ins.sample_ntopng_host_alerts(self.now),
        )
        end = int(self.now.timestamp())

        answer = handler(
            seen(
                f"/lua/rest/v2/get/host/alert/list.lua?ifid=0&epoch_begin=0&epoch_end={end}",
                **self.login,
            )
        )

        assert [item["family"] for item in body(answer)["rsp"]["records"]] == ["host", "host"]

    def test_every_one_of_them_sends_a_login_it_refuses_to_the_login_page(self) -> None:
        answer = self.handler()(seen("/lua/rest/v2/get/host/active.lua?ifid=0"))

        assert answer.status == 302

    def test_the_samples_have_what_the_collectors_read(self) -> None:
        hosts = stand_ins.sample_ntopng_hosts(self.now)
        flows = stand_ins.sample_ntopng_flow_alerts(self.now)
        hosts_alerts = stand_ins.sample_ntopng_host_alerts(self.now)

        assert len({item["ip"] for item in hosts}) == len(hosts)
        assert all(
            {"ip", "mac", "name", "bytes", "thpt", "num_flows"} <= set(item) for item in hosts
        )
        assert len({item["row_id"] for item in flows + hosts_alerts}) == 5
        assert all({"tstamp", "severity", "msg", "alert_id"} <= set(item) for item in flows)
        assert all(item["family"] == "flow" for item in flows)


class TestCrowdsec:
    handler = staticmethod(stand_ins.crowdsec("right-key"))

    def test_it_has_no_decisions_for_an_address(self) -> None:
        answer = self.handler(seen("/v1/decisions", **{"x-api-key": "right-key"}))

        assert (answer.status, answer.body) == (200, "null")

    def test_it_refuses_another_key(self) -> None:
        answer = self.handler(seen("/v1/decisions", **{"x-api-key": "wrong"}))

        assert (answer.status, body(answer)) == (403, {"message": "access forbidden"})
        assert self.handler(seen("/v1/decisions")).status == 403

    def test_it_has_nothing_elsewhere(self) -> None:
        assert self.handler(seen("/other", **{"x-api-key": "right-key"})).status == 404

    def test_it_gives_the_decisions_of_the_origins_asked_for(self) -> None:
        handler = stand_ins.crowdsec("right-key", stand_ins.sample_crowdsec_decisions())
        asked = seen(
            "/v1/decisions?origins=crowdsec,cscli,cscli-import,console",
            **{"x-api-key": "right-key"},
        )

        answer = handler(asked)

        assert (answer.status, [item["id"] for item in body(answer)]) == (
            200,
            [101, 102, 103, 105],
        )
        assert answer.headers == {"Content-Type": "application/json"}

    def test_it_gives_only_the_origin_asked_for(self) -> None:
        handler = stand_ins.crowdsec("right-key", stand_ins.sample_crowdsec_decisions())

        answer = handler(seen("/v1/decisions?origins=CAPI", **{"x-api-key": "right-key"}))

        assert [item["id"] for item in body(answer)] == [104]

    def test_it_has_nothing_for_an_origin_without_decisions(self) -> None:
        handler = stand_ins.crowdsec("right-key", stand_ins.sample_crowdsec_decisions())

        answer = handler(seen("/v1/decisions?origins=lists:tor", **{"x-api-key": "right-key"}))

        assert (answer.status, answer.body) == (200, "null")

    def test_a_question_about_an_address_has_no_decisions_even_when_it_has_some(self) -> None:
        handler = stand_ins.crowdsec("right-key", stand_ins.sample_crowdsec_decisions())

        answer = handler(seen("/v1/decisions?ip=192.0.2.1", **{"x-api-key": "right-key"}))

        assert (answer.status, answer.body) == (200, "null")

    def test_the_samples_are_numbered_and_each_has_what_the_collector_reads(self) -> None:
        samples = stand_ins.sample_crowdsec_decisions()

        assert len({item["id"] for item in samples}) == len(samples)
        assert all(
            {"origin", "type", "scope", "value", "duration"} <= set(item) for item in samples
        )


def post(path: str, content: object, **headers: str) -> Seen:
    return Seen("POST", path, headers, json.dumps(content).encode())


class TestWazuh:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    login: ClassVar[dict[str, str]] = {"authorization": basic("a-user", "a-password")}

    def handler(self) -> Handler:
        return stand_ins.wazuh(
            "a-user",
            "a-password",
            stand_ins.sample_wazuh_alerts(self.now),
            stand_ins.sample_wazuh_agents(self.now),
        )

    def token(self) -> str:
        answer = self.handler()(
            Seen("POST", "/security/user/authenticate?raw=true", self.login, b"")
        )
        assert (answer.status, answer.headers) == (200, {"Content-Type": "text/plain"})
        return str(answer.body)

    def bearer(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token()}"}

    def test_the_manager_gives_a_token_for_the_login_and_refuses_another(self) -> None:
        refused = self.handler()(
            Seen(
                "POST", "/security/user/authenticate", {"authorization": basic("a-user", "x")}, b""
            )
        )

        assert self.token().count(".") == 2
        assert (refused.status, body(refused)["title"]) == (401, "Unauthorized")

    def test_the_manager_says_which_version_it_is_to_a_token(self) -> None:
        answer = self.handler()(seen("/", **self.bearer()))

        assert body(answer)["data"]["api_version"] == "4.9.2"

    def test_the_indexer_says_which_version_it_is_to_the_login(self) -> None:
        answer = self.handler()(seen("/", **self.login))

        assert body(answer)["version"]["number"] == "7.10.2"

    @pytest.mark.parametrize(
        "headers", [{}, {"authorization": "Bearer wrong"}, {"authorization": "Basic wrong"}]
    )
    def test_it_refuses_a_request_that_signs_in_some_other_way(
        self, headers: dict[str, str]
    ) -> None:
        for path in ("/", "/agents", "/wazuh-alerts-*/_search"):
            assert self.handler()(seen(path, **headers)).status == 401

    def test_it_lists_the_agents_to_a_token_with_the_limit_and_fields_asked_for(self) -> None:
        answer = self.handler()(seen("/agents?limit=2&select=id,status", **self.bearer()))

        data = body(answer)["data"]
        assert data["affected_items"] == [
            {"id": "000", "status": "active"},
            {"id": "001", "status": "active"},
        ]
        assert (data["total_affected_items"], data["total_failed_items"]) == (5, 0)

    def test_it_lists_every_field_of_every_agent_when_not_told_otherwise(self) -> None:
        answer = self.handler()(seen("/agents", **self.bearer()))

        items = body(answer)["data"]["affected_items"]
        assert [item["id"] for item in items] == ["000", "001", "002", "003", "004"]
        assert items[1]["name"] == "web1"

    def test_it_searches_the_alerts_newest_first_and_only_as_far_back_as_asked(self) -> None:
        asked = {
            "size": 10,
            "query": {"range": {"timestamp": {"gte": "2026-10-26T11:30:00.000Z"}}},
        }

        answer = self.handler()(post("/wazuh-alerts-*/_search", asked, **self.login))

        hits = body(answer)["hits"]["hits"]
        assert [hit["_id"] for hit in hits] == [
            "wz-alert-1",
            "wz-alert-2",
            "wz-alert-3",
            "wz-alert-4",
        ]

    def test_it_gives_no_more_alerts_than_the_size_asked_for(self) -> None:
        asked = {"size": 2, "query": {"range": {"timestamp": {"gte": "2026-10-26T00:00:00Z"}}}}

        answer = self.handler()(post("/wazuh-alerts-*/_search", asked, **self.login))

        assert [hit["_id"] for hit in body(answer)["hits"]["hits"]] == ["wz-alert-1", "wz-alert-2"]

    def test_a_search_with_no_query_finds_every_alert(self) -> None:
        answer = self.handler()(Seen("POST", "/wazuh-alerts-%2A/_search", self.login, b""))

        assert len(body(answer)["hits"]["hits"]) == 5

    def test_it_has_nothing_elsewhere_and_a_search_is_a_post(self) -> None:
        assert self.handler()(seen("/other", **self.login)).status == 404
        assert self.handler()(seen("/other", **self.bearer())).status == 404
        assert self.handler()(seen("/wazuh-alerts-*/_search", **self.login)).status == 404

    def test_the_sample_alerts_are_dated_back_from_the_time_given(self) -> None:
        stamps = [hit["_source"]["timestamp"] for hit in stand_ins.sample_wazuh_alerts(self.now)]  # type: ignore[index]

        assert stamps[0] == "2026-10-26T11:58:00.123+0000"
        assert stamps[-1] == "2026-10-26T10:00:00.123+0000"


class TestOpnsense:
    credentials: ClassVar[dict[str, str]] = {"authorization": basic("a-key", "a-secret")}

    def handler(self, *services: str) -> Handler:
        return stand_ins.opnsense("a-key", "a-secret", services)

    def test_it_says_which_version_it_is(self) -> None:
        answer = self.handler()(
            seen("/api/diagnostics/system/system_information", **self.credentials)
        )

        assert answer.status == 200
        assert body(answer) == {
            "name": "fw.home.arpa",
            "versions": ["OPNsense 25.7.1-amd64"],
        }

    def test_it_refuses_another_key_or_secret(self) -> None:
        path = "/api/diagnostics/system/system_information"
        for authorization in (basic("a-key", "wrong"), basic("wrong", "a-secret"), None):
            headers = {} if authorization is None else {"authorization": authorization}
            answer = self.handler()(seen(path, **headers))
            assert (answer.status, body(answer)) == (
                401,
                {"status": 401, "message": "Authentication Failed"},
            )

    def test_the_services_it_has_are_running_and_the_others_are_not_installed(self) -> None:
        handler = self.handler("suricata", "openvpn")
        paths = {module.key: module.path for module in registry.OPNSENSE_MODULES}

        assert handler(seen(paths["suricata"], **self.credentials)).status == 200
        assert body(handler(seen(paths["openvpn"], **self.credentials))) == {"status": "running"}
        assert handler(seen(paths["crowdsec"], **self.credentials)).status == 404
        assert handler(seen("/api/unknown", **self.credentials)).status == 404


class TestOpnsenseTimeAndLog:
    credentials: ClassVar[dict[str, str]] = {"authorization": basic("a-key", "a-secret")}

    def handler(self, **options: Any) -> Handler:
        return stand_ins.opnsense("a-key", "a-secret", (), **options)

    def test_its_clock_shows_the_time_the_way_opnsense_does(self) -> None:
        answer = self.handler()(seen("/api/diagnostics/system/system_time", **self.credentials))

        shown = body(answer)["datetime"]
        words = shown.split()
        assert len(words) == 6
        assert words[4] == "XYZ"
        assert datetime.strptime(" ".join([*words[1:4], words[5]]), "%b %d %H:%M:%S %Y")

    def test_its_clock_can_be_in_another_time_zone(self) -> None:
        zone = timedelta(hours=-3)
        answer = self.handler(zone=zone)(
            seen("/api/diagnostics/system/system_time", **self.credentials)
        )

        words = body(answer)["datetime"].split()
        shown = datetime.strptime(" ".join([*words[1:4], words[5]]), "%b %d %H:%M:%S %Y")
        difference = shown - (datetime.now(UTC) + zone).replace(tzinfo=None)
        assert abs(difference) < timedelta(seconds=5)

    def test_its_log_is_empty_unless_it_is_given_lines(self) -> None:
        answer = self.handler()(seen("/api/diagnostics/firewall/log", **self.credentials))

        assert (answer.status, body(answer)) == (200, [])

    def test_its_log_has_the_lines_it_is_given_up_to_the_limit_asked_for(self) -> None:
        lines = [{"action": "block"}, {"action": "pass"}, {"action": "block"}]
        handler = self.handler(firewall_log=lines)

        everything = handler(seen("/api/diagnostics/firewall/log", **self.credentials))
        two = handler(seen("/api/diagnostics/firewall/log?limit=2", **self.credentials))

        assert body(everything) == lines
        assert body(two) == lines[:2]

    def test_the_time_and_the_log_need_the_key_too(self) -> None:
        for path in ("/api/diagnostics/system/system_time", "/api/diagnostics/firewall/log"):
            assert self.handler()(seen(path)).status == 401


class TestOpnsenseSuricataAlerts:
    credentials: ClassVar[dict[str, str]] = {"authorization": basic("a-key", "a-secret")}
    alerts: ClassVar[list[dict[str, object]]] = [{"alert": "one"}, {"alert": "two"}]

    def handler(self, services: tuple[str, ...] = ("suricata",)) -> Handler:
        return stand_ins.opnsense("a-key", "a-secret", services, suricata_alerts=self.alerts)

    @staticmethod
    def search(rows: object | None = None, method: str = "POST") -> Seen:
        body = b"" if rows is None else json.dumps({"rowCount": rows}).encode()
        return Seen(
            method, "/api/ids/service/query_alerts", TestOpnsenseSuricataAlerts.credentials, body
        )

    def test_a_search_answers_with_the_alerts_up_to_the_rows_asked_for(self) -> None:
        everything = self.handler()(self.search(10))
        one = self.handler()(self.search(1))

        assert (everything.status, body(everything)["rows"]) == (200, self.alerts)
        assert body(everything)["rowCount"] == 2
        assert body(one)["rows"] == self.alerts[:1]

    @pytest.mark.parametrize("asked", [None, 0, -1, "ten", 1.5])
    def test_a_search_that_doesnt_say_how_many_rows_gets_all_of_them(self, asked: object) -> None:
        answer = self.handler()(self.search(asked))

        assert body(answer)["rows"] == self.alerts

    def test_a_search_with_a_body_that_isnt_json_gets_all_of_them_too(self) -> None:
        asked = Seen("POST", "/api/ids/service/query_alerts", self.credentials, b"rowCount=1")

        assert body(self.handler()(asked))["rows"] == self.alerts

    def test_asked_any_other_way_it_answers_with_an_empty_list_as_opnsense_does(self) -> None:
        answer = self.handler()(self.search(10, method="GET"))

        assert (answer.status, body(answer)) == (200, [])

    def test_without_suricata_it_is_not_there(self) -> None:
        answer = self.handler(())(self.search(10))

        assert answer.status == 404

    def test_it_needs_the_key_too(self) -> None:
        asked = Seen("POST", "/api/ids/service/query_alerts", {}, b"")

        assert self.handler()(asked).status == 401


class TestOpnsenseDevices:
    credentials: ClassVar[dict[str, str]] = {"authorization": basic("a-key", "a-secret")}
    table: ClassVar[list[dict[str, object]]] = [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.9"}]

    def handler(self, *services: str, **options: Any) -> Handler:
        return stand_ins.opnsense("a-key", "a-secret", services, **options)

    def test_its_arp_table_is_empty_unless_it_is_given_entries(self) -> None:
        path = "/api/diagnostics/interface/get_arp"

        assert body(self.handler()(seen(path, **self.credentials))) == []
        given = self.handler(arp_table=self.table)(seen(path, **self.credentials))
        assert (given.status, body(given)) == (200, self.table)

    @pytest.mark.parametrize(
        ("service", "path", "option"),
        [
            ("dnsmasq", "/api/dnsmasq/leases/search", "dnsmasq_leases"),
            ("kea", "/api/kea/leases4/search", "kea_leases"),
        ],
    )
    def test_the_leases_of_a_dhcp_server_are_there_if_it_is_installed(
        self, service: str, path: str, option: str
    ) -> None:
        leases = [{"hwaddr": "aa:bb:cc:00:11:22", "address": "192.168.1.9"}]
        installed = self.handler(service, **{option: leases})
        missing = self.handler(**{option: leases})

        answer = installed(seen(path, **self.credentials))
        assert (answer.status, body(answer)) == (
            200,
            {"total": 1, "rowCount": 1, "current": 1, "rows": leases},
        )
        assert missing(seen(path, **self.credentials)).status == 404

    def test_one_dhcp_server_is_not_the_other(self) -> None:
        handler = self.handler("dnsmasq")

        assert handler(seen("/api/kea/leases4/search", **self.credentials)).status == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/api/diagnostics/interface/get_arp",
            "/api/dnsmasq/leases/search",
            "/api/kea/leases4/search",
        ],
    )
    def test_they_need_the_key_too(self, path: str) -> None:
        assert self.handler("dnsmasq", "kea")(seen(path)).status == 401


class TestSampleSuricataAlerts:
    def test_they_are_two_recent_alerts_that_the_collector_reads(self) -> None:
        events = parse_alerts(list(stand_ins.sample_suricata_alerts()))

        assert [event.severity for event in events] == [Severity.MEDIUM, Severity.LOW]
        now = datetime.now(UTC)
        assert all(
            timedelta(0) < now - event.occurred_at < timedelta(minutes=1) for event in events
        )
        assert len({event.fingerprint for event in events}) == 2


class TestSampleFirewallLog:
    def test_it_is_three_recent_lines_that_the_collector_reads_newest_first(self) -> None:
        now = datetime.now(UTC)

        events = parse(list(stand_ins.sample_firewall_log()), timedelta(0), now)

        assert [event.severity for event in events] == [Severity.LOW, Severity.INFO, Severity.INFO]
        assert [now - event.occurred_at < timedelta(seconds=30) for event in events] == [True] * 3
        assert [event.occurred_at for event in events] == sorted(
            (event.occurred_at for event in events), reverse=True
        )
        assert len({event.fingerprint for event in events}) == 3


class TestZenarmor:
    handler = staticmethod(stand_ins.zenarmor("right-key"))

    def test_it_lists_policies_for_the_key(self) -> None:
        answer = self.handler(seen("/policies", authorization=basic("right-key", "")))

        assert (answer.status, body(answer)) == (200, {"policies": []})

    def test_it_refuses_another_key_and_other_paths(self) -> None:
        assert self.handler(seen("/policies", authorization=basic("wrong", ""))).status == 401
        assert self.handler(seen("/policies")).status == 401
        assert self.handler(seen("/other", authorization=basic("right-key", ""))).status == 401


@pytest.fixture
def running():
    stand_ins_started = StandIns()
    try:
        yield stand_ins_started
    finally:
        stand_ins_started.stop_all()


def fetch(url: str, **headers: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


class TestStandIns:
    def test_ntopng_and_crowdsec_answer_over_plain_http(self, running: StandIns) -> None:
        ntopng = running.start("ntopng", token="a-token")
        crowdsec = running.start("crowdsec", api_key="a-key")

        assert ntopng.url.startswith("http://127.0.0.1:")
        assert ntopng.fingerprint is None
        assert (
            fetch(
                ntopng.url + "/lua/rest/v2/get/ntopng/interfaces.lua", Authorization="Token a-token"
            )[0]
            == 200
        )
        assert fetch(crowdsec.url + "/v1/decisions", **{"X-Api-Key": "a-key"}) == (200, "null")
        status, text = fetch(crowdsec.url + "/v1/decisions?origins=cscli", **{"X-Api-Key": "a-key"})
        assert (status, [item["id"] for item in json.loads(text)]) == (200, [102])

    @pytest.mark.parametrize("kind", ["opnsense", "zenarmor"])
    def test_opnsense_and_zenarmor_have_a_certificate_of_their_own(
        self, running: StandIns, kind: stand_ins.Kind
    ) -> None:
        started = running.start(kind, api_key="a-key", api_secret="a-secret")
        origin = netguard.parse_origin(started.url, allow_http=False)

        presented = asyncio.run(
            netguard.look_up_certificate(netguard.HOME_NETWORK_AND_LOOPBACK, origin)
        )

        assert started.url.startswith("https://127.0.0.1:")
        assert started.fingerprint == presented.fingerprint
        assert presented.names == ["fw.home.arpa", "127.0.0.1"]

    def test_wazuh_has_a_certificate_of_its_own_and_answers_to_the_login_it_was_started_with(
        self, running: StandIns
    ) -> None:
        started = running.start("wazuh", username="a-user", password="a-password")
        origin = netguard.parse_origin(started.url, allow_http=False)

        presented = asyncio.run(
            netguard.look_up_certificate(netguard.HOME_NETWORK_AND_LOOPBACK, origin)
        )

        assert started.url.startswith("https://127.0.0.1:")
        assert started.fingerprint == presented.fingerprint
        assert presented.names == ["wazuh.home.arpa", "127.0.0.1"]

    def test_each_is_a_server_of_its_own(self, running: StandIns) -> None:
        first = running.start("ntopng", token="a")
        second = running.start("ntopng", token="b")

        assert first.id != second.id
        assert first.url != second.url

    def test_they_all_stop_together(self, running: StandIns) -> None:
        started = running.start("crowdsec", api_key="a-key")
        assert fetch(started.url + "/v1/decisions")[0] == 403

        running.stop_all()

        with pytest.raises(urllib.error.URLError):
            fetch(started.url + "/v1/decisions")
        running.stop_all()


def test_a_stub_server_is_the_same_class_the_tests_use() -> None:
    from tests import stubs

    assert stubs.StubServer is StubServer
