"""The worker: the process that collects from the integrations on a schedule. It runs next to
the API, as its own program in the container, so a slow integration or a crash in a collector
never takes the web app with it. They share the database and nothing else.

    python -m app.worker
"""

import asyncio

from app import logs
from app.collectors.scheduler import Scheduler
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.incidents import run as incidents
from app.integrations import netguard
from app.integrations.apilog import ApiLogRecorder
from app.secret_key import load_secret_key


def collecting(settings: Settings) -> bool:
    """Whether this worker collects. Tests and the end-to-end harness decide for themselves when a
    collector runs, so there the worker only says it is alive."""
    return settings.collectors_enabled and settings.environment != "test"


def build(settings: Settings) -> Scheduler:
    """The scheduler for a real install."""
    new_session = get_sessionmaker()
    return Scheduler(
        settings,
        new_session,
        ApiLogRecorder(new_session),
        netguard.HOME_NETWORK,
        enabled=collecting(settings),
    )


async def serve(settings: Settings) -> None:
    """Collects, and files what is collected into incidents, until cancelled."""
    async with asyncio.TaskGroup() as work:
        work.create_task(build(settings).run())
        work.create_task(incidents.run(get_sessionmaker(), enabled=collecting(settings)))


def main() -> None:
    settings = get_settings()
    logs.configure(settings, secrets=[load_secret_key(settings).get_secret_value()])
    asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
