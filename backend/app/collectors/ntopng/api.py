"""Reading from ntopng's REST API (version 2) for a collector: signed in the way the connection
says, and what to say when the answer isn't one a collector can use.

Every answer is an object with ``rc`` (0 when it worked), ``rc_str`` and ``rsp``, the data. ntopng
answers a login it refuses with a redirect to its login page, not with a 401."""

from collections.abc import Mapping
from http import HTTPStatus

from app.collectors.base import CollectorFailed, Context
from app.integrations import probes
from app.integrations.client import CallFailed

PRODUCT = "ntopng"


def interface(context: Context) -> str:
    """The interface the connection watches, as ntopng's ``ifid`` parameter."""
    return str(context.target.options["interface_id"])


async def read(context: Context, path: str, query: Mapping[str, str]) -> object:
    """Asks ntopng for something and returns the ``rsp`` of its answer. Raises
    ``CollectorFailed``, with a reason fit for the status page, if it refused or answered with
    something else."""
    reply = await probes.ntopng_get(context.client, context.target, path, query)
    if 300 <= reply.status < 400:
        raise CollectorFailed(probes.NTOPNG_LOGIN_REFUSED)
    if reply.status == HTTPStatus.BAD_REQUEST:
        raise CollectorFailed(await _refused(context))
    if bad := probes.problem(reply, PRODUCT):
        raise CollectorFailed(bad.message)
    answer = probes.as_object(reply.json())
    if answer is None or "rsp" not in answer:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    if answer.get("rc") != 0:
        raise CollectorFailed(
            f"ntopng answered with the error {probes.fact(answer.get('rc_str'))}."
        )
    return answer["rsp"]


async def _refused(context: Context) -> str:
    """Why ntopng answered a request with 400, which it does for an interface it doesn't have: it
    is asked which ones it has, so that the interface that was chosen can be named and the ones
    to choose from listed."""
    wanted = int(context.target.options["interface_id"])
    try:
        listed = await probes.ntopng_interfaces(context.client, context.target)
    except CallFailed:
        listed = None
    if isinstance(listed, list) and wanted not in {item.ifid for item in listed}:
        return (
            f"ntopng has no interface {wanted}, so it refused the request. It has: "
            f"{probes.interface_names(listed)}. Choose one under Interface in the connection's "
            "settings."
        )
    return f"{PRODUCT} refused the request (HTTP 400)."
