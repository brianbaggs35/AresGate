"""How many alerts ntopng holds, by how serious and by what kind, as metrics, so the baselines can
learn how many a quiet day has and a flood stands out.

``GET /lua/rest/v2/get/alert/severity/counters.lua`` and ``.../alert/type/counters.lua`` take the
interface (``ifid``) and answer with an array in ``rsp`` with an object for each group: its
``count``, the ``entity_label`` of what the alert was about (``Flow``, ``Host``, ``Interface``),
the ``alert_id`` and its ``name``: the severity's, for the first, and the kind's, for the second.
They count the alerts of every sort ntopng keeps, the flow and host ones that ``alerts.py`` reads
among them.

A count is a gauge, not a rising counter: it is how many alerts ntopng's alert database holds when
it is read, which is as far back as ntopng keeps them. The scripts take only the interface: they
never read a time range (they make their store without the request's filters), so the window that
is still sent is for a ntopng that does read it, and the counts are not "the last day". A severity
or a kind with none has no reading, so a chart sees it as a gap, not a zero; the ``name`` is in
ntopng's language, which is English unless it has been changed.

Read from ntopng's source (``scripts/lua/rest/v2/get/alert/{severity,type}/counters.lua`` and
``alert_store/all_alert_store.lua``), which the documentation has no page for. Not tried against a
live ntopng. The user must be allowed to see alerts. The scripts ask ntopng's own alert database
and fail, in ntopng, if that can't answer; ntopng then redirects to its error page, which
``probes.ntopng_redirected`` tells from a refused login and reports with what the script said."""

from datetime import timedelta

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.ntopng.api import PRODUCT, interfaces, names, read
from app.collectors.readings import Readings, number
from app.integrations import probes

SEVERITY = "/lua/rest/v2/get/alert/severity/counters.lua"
KIND = "/lua/rest/v2/get/alert/type/counters.lua"
WINDOW = timedelta(days=1)
MAX_KINDS = 100


class AlertCounters(Collector):
    key = "ntopng-alert-counters"
    title = "Alert counts"
    summary = (
        "Reads how many alerts ntopng holds, by severity and by kind, every five minutes, as "
        "metrics."
    )
    interval = timedelta(minutes=5)
    timeout = timedelta(minutes=1)
    integration = "ntopng"
    connection = "api"

    async def collect(self, context: Context) -> Outcome:
        ports = await names(context)
        readings = Readings(context)
        for ifid in await interfaces(context):
            port = ports.get(ifid, str(ifid))
            query = {
                "ifid": str(ifid),
                "epoch_begin": str(int((context.now - WINDOW).timestamp())),
                "epoch_end": str(int(context.now.timestamp())),
            }
            for path, metric, label in (
                (SEVERITY, "alerts.by_severity", "severity"),
                (KIND, "alerts.by_kind", "kind"),
            ):
                rows = probes.as_array(await read(context, path, query))
                if rows is None:
                    raise CollectorFailed(probes.unexpected(PRODUCT).message)
                for (entity, name), count in _totals(rows).items():
                    readings.add(metric, count, interface=port, entity=entity, **{label: name})
        return Outcome(items=await readings.save())


def _totals(rows: list[object]) -> dict[tuple[str, str], float]:
    """The count for each entity and name. ntopng counts a severity once for each kind of alert
    that has it, so the groups that share a name are added up."""
    totals: dict[tuple[str, str], float] = {}
    for row in rows[:MAX_KINDS]:
        group = probes.as_object(row)
        count = number(group.get("count")) if group else None
        if group is None or count is None:
            continue
        name = traffic.text(group, "name")
        entity = traffic.text(group, "entity_label") or "Other"
        if name:
            totals[entity, name] = totals.get((entity, name), 0.0) + count
    return totals
