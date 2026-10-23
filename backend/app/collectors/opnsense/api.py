"""Reading from OPNsense's API for a collector: the key and secret as HTTP basic authentication,
and what to say when the answer isn't one a collector can use."""

from collections.abc import Mapping

from app.collectors.base import CollectorFailed, Context
from app.integrations import probes

PRODUCT = "OPNsense"


async def read(context: Context, path: str, query: Mapping[str, str] | None = None) -> object:
    """Asks OPNsense for something and returns the JSON it answered. Raises ``CollectorFailed``,
    with a reason fit for the status page, if it refused or answered with something else."""
    credentials = (context.target.secrets["api_key"], context.target.secrets["api_secret"])
    reply = await context.client.request("GET", path, query=query, auth=credentials)
    if bad := probes.problem(reply, PRODUCT):
        raise CollectorFailed(bad.message)
    data = reply.json()
    if data is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return data
