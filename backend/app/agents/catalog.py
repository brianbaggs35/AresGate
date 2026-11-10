"""What an agent can be made from. A template says what an agent looks at first, what more it may
ask to look at, how often it is sensible to run it and whether it tests the network. The owner
makes an agent from one and adds their own instructions; the code never changes for it."""

from dataclasses import dataclass, field
from typing import Final

from app.ai.tools import Args


@dataclass(frozen=True)
class Lookup:
    """One look at what AresGate knows: the name of a tool (app/ai/tools.py, or ``scan_exposure``
    in app/agents/probe.py) and what it is asked for."""

    tool: str
    args: Args = field(default_factory=Args)


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    tagline: str
    description: str
    # The name of an icon the web app knows, so that each kind of agent looks like itself.
    icon: str
    # What the agent is told it is for, the same for every agent made from the template.
    brief: str
    # The owner's instructions to start from, which they may change.
    goal: str
    # What it looks at first, and what else it may ask the model to have looked at.
    first: tuple[Lookup, ...]
    asks: tuple[str, ...]
    # How many minutes between runs, to start with, or None to run only when asked.
    interval_minutes: int | None
    # Whether it sends probes to devices on the network. Such an agent is never on a schedule, and
    # the owner has to allow it, on the agent, before it sends anything.
    active: bool = False


THREAT_HUNTER: Final = Template(
    key="threat_hunter",
    name="Threat hunter",
    tagline="Reviews the alerts and incidents for anything worth your attention",
    description=(
        "Reads the incidents that are open, the latest alerts and who the firewall turned away "
        "most, follows up on what looks wrong, and says what, if anything, needs you."
    ),
    icon="radar",
    brief=(
        "You hunt for threats. Look at the open incidents, the latest alerts and the sources the "
        "firewall turned away most, follow up on what looks serious, and report what is worth "
        "the owner's attention and what is only noise."
    ),
    goal="Tell me about anything that looks like a real compromise, and ignore routine scanning.",
    first=(
        Lookup("open_incidents", Args(limit=5)),
        Lookup("alerts", Args(hours=24, limit=10)),
        Lookup("blocked_sources", Args(hours=24, limit=5)),
    ),
    asks=("open_incidents", "incident", "alerts", "blocked_sources", "device"),
    interval_minutes=60,
)
INTELLIGENCE_ANALYST: Final = Template(
    key="intelligence_analyst",
    name="Intelligence analyst",
    tagline="Checks who is behind the traffic against what VirusTotal has reported",
    description=(
        "Takes the addresses behind the open incidents and the most blocked sources, reads what "
        "AresGate has kept of VirusTotal's reports on them, and says which are known to be bad, "
        "which are clean and which nobody has asked about yet."
    ),
    icon="telescope",
    brief=(
        "You collect threat intelligence. For the addresses behind the open incidents and the most "
        "blocked sources, look at what is known of them, say which are known to be malicious, "
        "which are clean, and which have no report yet."
    ),
    goal="Point out addresses in my incidents that several security engines flag.",
    first=(
        Lookup("open_incidents", Args(limit=5)),
        Lookup("blocked_sources", Args(hours=72, limit=5)),
    ),
    asks=("open_incidents", "incident", "blocked_sources", "reputation"),
    interval_minutes=360,
)
HEALTH_WATCH: Final = Template(
    key="health_watch",
    name="Health watch",
    tagline="Notices when an integration or collector stops working",
    description=(
        "Looks at whether each integration and its collectors are working, and tells you what "
        "went wrong and what to try, before a gap in the data costs you an alert."
    ),
    icon="heart-pulse",
    brief=(
        "You watch the health of AresGate's own connections. Look at each integration and its "
        "collectors, say which are failing and why, and what the owner can do about it."
    ),
    goal="Tell me what is failing and what to try first.",
    first=(Lookup("integrations"),),
    asks=("integrations",),
    interval_minutes=120,
)
EXPOSURE_SCANNER: Final = Template(
    key="exposure_scanner",
    name="Exposure scanner",
    tagline="Tests your devices for services that should not be open",
    description=(
        "Connects to a short list of risky ports on the devices AresGate has seen at home, such "
        "as Telnet, remote desktop and open databases, and reports what answers. It only "
        "connects and never sends anything else. It tests your own network, only when you "
        "start it, and only once you have allowed it on the agent."
    ),
    icon="scan-search",
    brief=(
        "You test the home network for exposure. You are given which risky services answered on "
        "which devices. Explain which matter most and why, and what to do about each, in plain "
        "words. Never suggest attacking anything."
    ),
    goal="Rank what I should close first.",
    first=(Lookup("scan_exposure"),),
    asks=("device",),
    interval_minutes=None,
    active=True,
)

TEMPLATES: Final[tuple[Template, ...]] = (
    THREAT_HUNTER,
    INTELLIGENCE_ANALYST,
    HEALTH_WATCH,
    EXPOSURE_SCANNER,
)


def template(key: str) -> Template | None:
    return next((item for item in TEMPLATES if item.key == key), None)
