"""Reading from ntopng's REST API (version 2) for a collector: signed in the way the connection
says, and what to say when the answer isn't one a collector can use.

Every answer is an object with ``rc`` (0 when it worked), ``rc_str`` and ``rsp``, the data. ntopng
answers a login it refuses with a redirect to its login page, not with a 401."""

from collections.abc import Mapping
from http import HTTPStatus

from app.collectors.base import CollectorFailed, Context
from app.integrations import probes, registry
from app.integrations.client import CallFailed

PRODUCT = "ntopng"


async def interfaces(context: Context) -> list[int]:
    """The interfaces the connection reads, as ntopng's ``ifid`` parameter, lowest first. Where
    none is chosen, ntopng is asked which it has, and every one but the loopback is read."""
    chosen = registry.chosen_numbers(context.target.options["interface_id"])
    if chosen:
        return chosen
    listed = await probes.ntopng_interfaces(context.client, context.target)
    if isinstance(listed, probes.Verdict):
        raise CollectorFailed(listed.message)
    if not listed:
        raise CollectorFailed("ntopng lists no interfaces, so there is nothing to read.")
    return [item.ifid for item in probes.default_interfaces(listed)]


async def names(context: Context) -> dict[int, str]:
    """What the metrics and events call each of ntopng's interfaces, by ``ifid``: the name the
    system gives it (``eth0``). Asking is one request; an answer that can't be had leaves the
    names empty, and what is stored is then without a port name, not lost."""
    try:
        listed = await probes.ntopng_interfaces(context.client, context.target)
    except CallFailed:
        return {}
    if not isinstance(listed, list):
        return {}
    return {item.ifid: item.ifname for item in listed if item.ifname}


async def read(context: Context, path: str, query: Mapping[str, str]) -> object:
    """Asks ntopng for something and returns the ``rsp`` of its answer. Raises
    ``CollectorFailed``, with a reason fit for the status page, if it refused or answered with
    something else."""
    reply = await probes.ntopng_get(context.client, context.target, path, query)
    if 300 <= reply.status < 400:
        raise CollectorFailed(probes.ntopng_redirected(reply, path))
    if reply.status == HTTPStatus.BAD_REQUEST:
        raise CollectorFailed(await _refused(context, query.get("ifid", "")))
    if bad := probes.ntopng_problem(reply):
        raise CollectorFailed(bad.message)
    answer = probes.as_object(reply.json())
    if answer is None or "rsp" not in answer:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    if answer.get("rc") != 0:
        raise CollectorFailed(
            f"ntopng answered with the error {probes.fact(answer.get('rc_str'))}."
        )
    return answer["rsp"]


async def _refused(context: Context, asked: str) -> str:
    """Why ntopng answered a request with 400, which it does for an interface it doesn't have: it
    is asked which ones it has, so that the interface that was asked about can be named and the
    ones to choose from listed."""
    try:
        listed = await probes.ntopng_interfaces(context.client, context.target)
    except CallFailed:
        listed = None
    if isinstance(listed, list) and asked.isdigit() and int(asked) not in {i.ifid for i in listed}:
        return (
            f"ntopng has no interface {asked}, so it refused the request. It has: "
            f"{probes.interface_names(listed)}. Choose the interfaces to read under Interfaces "
            "in the connection's settings."
        )
    return f"{PRODUCT} refused the request (HTTP 400)."
