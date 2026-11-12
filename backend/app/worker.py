"""The worker: the process that collects from the integrations on a schedule. It runs next to
the API, as its own program in the container, so a slow integration or a crash in a collector
never takes the web app with it. They share the database and nothing else.

    python -m app.worker
"""

import asyncio

from app import logs
from app.agents import run as agents
from app.ai import gateway
from app.ai import run as ai
from app.alerts import notify
from app.collectors.scheduler import Scheduler
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.fingerbank import run as fingerbank
from app.incidents import run as incidents
from app.integrations import netguard
from app.integrations.apilog import ApiLogRecorder
from app.intel import run as intel
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
    """Collects, files what is collected into incidents, has the AI read them, runs the agents and
    tells the destinations of the ones that matter, until cancelled."""
    new_session = get_sessionmaker()
    recorder = ApiLogRecorder(new_session)
    context = gateway.context_for_worker(settings, recorder)
    async with asyncio.TaskGroup() as work:
        work.create_task(build(settings).run())
        work.create_task(incidents.run(new_session, enabled=collecting(settings)))
        work.create_task(ai.run(new_session, context, enabled=collecting(settings)))
        work.create_task(agents.run(new_session, context, enabled=collecting(settings)))
        work.create_task(intel.run(new_session, settings, recorder, enabled=collecting(settings)))
        work.create_task(
            fingerbank.run(new_session, settings, recorder, enabled=collecting(settings))
        )
        work.create_task(
            notify.run(
                settings,
                new_session,
                recorder,
                netguard.PUBLIC_INTERNET,
                enabled=collecting(settings),
            )
        )


def main() -> None:
    settings = get_settings()
    logs.configure(settings, secrets=[load_secret_key(settings).get_secret_value()])
    asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
