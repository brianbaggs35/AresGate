import asyncio
import json
import urllib.error
import urllib.request
from typing import ClassVar

import pytest

from app.integrations import netguard, registry
from e2e import stand_ins
from e2e.stand_ins import Answer, Handler, Seen, StandIns, StubServer


def seen(path: str, **headers: str) -> Seen:
    return Seen("GET", path, headers, b"")


def basic(user: str, password: str) -> str:
    return stand_ins._basic(user, password)  # pyright: ignore[reportPrivateUsage]


def body(answer: Answer) -> object:
    return json.loads(answer.body)


class TestNtopng:
    handler = staticmethod(stand_ins.ntopng("right-token"))

    def test_it_lists_its_interfaces_for_the_token(self) -> None:
        answer = self.handler(
            seen("/lua/rest/v2/get/ntopng/interfaces.lua", authorization="Token right-token")
        )

        assert answer.status == 200
        assert body(answer) == {"rc": 0, "rsp": [{"ifid": 0, "ifname": "eth0"}]}

    @pytest.mark.parametrize("authorization", ["Token wrong", "Bearer right-token", None])
    def test_it_sends_a_login_it_refuses_to_its_login_page(self, authorization: str | None) -> None:
        headers = {} if authorization is None else {"authorization": authorization}

        answer = self.handler(seen("/lua/rest/v2/get/ntopng/interfaces.lua", **headers))

        assert (answer.status, answer.headers) == (302, {"Location": "/lua/login.lua"})

    def test_it_sends_anything_else_to_the_login_page_too(self) -> None:
        answer = self.handler(seen("/other", authorization="Token right-token"))

        assert answer.status == 302


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
