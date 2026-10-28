"""What every ntopng collector says when ntopng won't do what it asks."""

import json
from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.collectors.base import Collector
from app.collectors.ntopng.alerts import Alerts
from app.collectors.ntopng.hosts import Hosts
from app.collectors.ntopng.interface import InterfaceTraffic
from app.config import Settings
from app.integrations import probes
from e2e.stand_ins import Answer, Seen, ntopng
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve

COLLECTORS = [Hosts, InterfaceTraffic, Alerts]


def refusing(seen: Seen) -> Answer:
    """A ntopng that has interface 0 and refuses every other request with a 400."""
    if seen.path.endswith("interfaces.lua"):
        return Answer(body=json.dumps({"rc": 0, "rc_str": "OK", "rsp": [{"ifid": 0}]}))
    return Answer(status=400)


def run(
    session: Session,
    settings: Settings,
    engine: Engine,
    serve: Serve,
    collector: Collector,
    handler: Callable[[Seen], Answer],
    interface_id: int = 0,
) -> str | None:
    """Runs the collector against a ntopng that answers with the handler, and says why it failed."""
    connect(session, settings, serve(handler).url, interface_id=interface_id)
    collect(settings, engine, collector)
    return health(session).last_error


@pytest.mark.parametrize("make", COLLECTORS)
class TestWhenNtopngRefuses:
    def test_a_login_it_refuses_is_a_redirect_to_its_login_page(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        refused = run(session, settings, engine, serve, make(), ntopng("another-token"))

        assert refused == probes.NTOPNG_LOGIN_REFUSED

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_login_it_says_no_to_is_not_accepted(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
        status: int,
    ) -> None:
        said = run(session, settings, engine, serve, make(), lambda seen: Answer(status=status))

        assert said is not None
        assert "didn't accept the credentials" in said

    def test_an_error_in_its_answer_is_named(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        def handle(seen: Seen) -> Answer:
            return Answer(body=json.dumps({"rc": -3, "rc_str": "NOT_GRANTED", "rsp": {}}))

        said = run(session, settings, engine, serve, make(), handle)

        assert said == "ntopng answered with the error NOT_GRANTED."

    def test_an_interface_it_does_not_have_is_named_and_the_ones_it_has_are_listed(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        said = run(session, settings, engine, serve, make(), ntopng(TOKEN), interface_id=7)

        assert said == (
            "ntopng has no interface 7, so it refused the request. It has: ID 0: eth0, "
            "ID 1: LAN (eth1). Choose one under Interface in the connection's settings."
        )

    def test_a_400_for_an_interface_it_has_is_just_a_400(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        said = run(session, settings, engine, serve, make(), lambda seen: refusing(seen))

        assert said == "ntopng refused the request (HTTP 400)."

    def test_a_400_when_it_cannot_even_list_its_interfaces_is_just_a_400(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        said = run(session, settings, engine, serve, make(), lambda seen: Answer(status=400))

        assert said == "ntopng refused the request (HTTP 400)."

    def test_a_400_when_the_list_request_breaks_is_just_a_400(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        def handle(seen: Seen) -> Answer:
            if seen.path.endswith("interfaces.lua"):
                return Answer(drop=True)
            return Answer(status=400)

        said = run(session, settings, engine, serve, make(), handle)

        assert said == "ntopng refused the request (HTTP 400)."

    @pytest.mark.parametrize("body", ["not json", "[]", '{"rc": 0}'])
    def test_an_answer_that_is_not_ntopngs_is_not_taken_for_it(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
        body: str,
    ) -> None:
        said = run(session, settings, engine, serve, make(), lambda seen: Answer(body=body))

        assert said == probes.unexpected("ntopng").message

    def test_a_ntopng_that_cannot_be_reached_fails_too(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        serve: Serve,
        make: Callable[[], Collector],
    ) -> None:
        said = run(session, settings, engine, serve, make(), lambda seen: Answer(drop=True))

        assert said is not None
