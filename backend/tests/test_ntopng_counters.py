from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.ntopng.counters import KIND, SEVERITY, AlertCounters
from app.config import Settings
from app.integrations import probes
from app.models import MetricSample, MetricSeries
from e2e.stand_ins import answers, ntopng, sample_ntopng_extras
from tests.ntopng import TOKEN, connect
from tests.opnsense import collect, health
from tests.stubs import Serve
from tests.test_ai_service import NOW


def stored(session: Session) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    session.expire_all()
    rows = session.execute(
        select(MetricSeries.name, MetricSeries.labels, MetricSample.value).join(
            MetricSeries, MetricSeries.id == MetricSample.series_id
        )
    )
    return {(name, tuple(sorted(labels.items()))): value for name, labels, value in rows}


def run(session: Session, settings: Settings, engine: Engine, serve: Serve, extras: Any) -> None:
    connect(session, settings, serve(ntopng(TOKEN, extras=extras)).url)
    collect(settings, engine, AlertCounters())


def test_it_reads_from_ntopng_and_is_one_of_the_collectors() -> None:
    assert AlertCounters.reads("ntopng", "api")
    assert not AlertCounters.reads("opnsense", "api")
    assert collectors.find("ntopng-alert-counters") is not None
    assert AlertCounters.interval == timedelta(minutes=5)
    assert AlertCounters.timeout <= AlertCounters.interval


def test_it_keeps_how_many_alerts_there_are_of_each_severity_and_kind(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    run(session, settings, engine, serve, sample_ntopng_extras(NOW))

    found = stored(session)
    where = (("entity", "Flow"), ("interface", "eth0"))
    # The severity ntopng counts for two kinds of alert is one reading.
    assert found["alerts.by_severity", (*where, ("severity", "Error"))] == 7
    assert (
        found[
            "alerts.by_severity",
            (("entity", "Host"), ("interface", "eth0"), ("severity", "Warning")),
        ]
        == 3
    )
    assert found["alerts.by_kind", (*where, ("kind", "Blacklisted Flow"))] == 5
    assert health(session).last_items == 4


def test_a_group_that_is_not_an_object_has_no_count_or_has_no_name_is_left_out(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    rows = [
        "text",
        {"count": "many", "name": "Error"},
        {"count": 4, "name": ""},
        {"count": 2, "name": "Notice"},
    ]
    extras = {SEVERITY: answers(rows), KIND: answers([])}

    run(session, settings, engine, serve, extras)

    assert stored(session) == {
        (
            "alerts.by_severity",
            (("entity", "Other"), ("interface", "eth0"), ("severity", "Notice")),
        ): 2
    }


def test_an_answer_that_is_not_a_list_is_not_taken_for_one(
    session: Session, settings: Settings, engine: Engine, serve: Serve
) -> None:
    run(session, settings, engine, serve, {SEVERITY: answers({}), KIND: answers([])})

    assert health(session).last_error == probes.unexpected("ntopng").message
