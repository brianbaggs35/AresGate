"""What an agent can be made from. A template says what an agent looks at first, what more it may
ask to look at, how often it is sensible to run it and whether it tests the network. The owner
makes an agent from one and adds their own instructions; the code never changes for it."""

from dataclasses import dataclass, field
from typing import Final

from app.ai.tools import Args


@dataclass(frozen=True)
class Lookup:
    """One look at what AresGate knows: the name of a tool (app/ai/tools.py, or ``scan_exposure``
    in app/agents/probe.py, or ``read_services`` in app/agents/fingerprint.py) and what it is asked
    for."""

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
    # What it needs in order to be useful, by the name of a check (app/agents/readiness.py), and
    # the steps to take to set it up, for someone making the agent for the first time.
    # Whether it suggests tidying incidents, which the owner applies (or it does itself when the
    # agents are set to, for the surest of them), always in ways that can be taken back.
    proposes: bool = False
    needs: tuple[str, ...] = ()
    setup: tuple[str, ...] = ()


# The setup step every kind that asks the AI shares.
CHOOSE_AI: Final = "Choose the AI the agents ask under Settings > Agents."


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
    asks=(
        "open_incidents",
        "incident",
        "alerts",
        "blocked_sources",
        "device",
        "noisy_alerts",
        "targeted_ports",
        "new_devices",
        "repeated_incidents",
    ),
    interval_minutes=60,
    needs=("ai", "alerts"),
    setup=(
        "Connect at least one source of alerts under Integrations: OPNsense with Suricata, "
        "Wazuh or CrowdSec each give it something to read.",
        "Choose the AI the agents ask under Settings > Agents. A small, cheap model is plenty.",
        "Start it once by hand to see what it makes of your network, then leave it on its hourly "
        "schedule.",
    ),
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
    asks=("open_incidents", "incident", "blocked_sources", "reputation", "noisy_alerts"),
    interval_minutes=360,
    needs=("ai", "intel", "alerts"),
    setup=(
        "Make a free VirusTotal account and copy its API key from your profile.",
        "Add the key under Integrations > VirusTotal. AresGate asks about addresses itself, within "
        "the free key's daily limit; this agent only reads what it kept.",
        CHOOSE_AI,
    ),
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
    needs=("ai", "integrations"),
    setup=(
        "Connect the integrations you use under Integrations: this agent watches whichever are "
        "connected.",
        CHOOSE_AI,
    ),
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
    needs=("ai", "devices"),
    setup=(
        "Connect OPNsense or ntopng under Integrations, so that AresGate knows which devices are "
        "on the network. It tests only those.",
        "Edit the agent and allow it to test your network: it does nothing until you do, and it "
        "only ever connects to a short list of risky ports.",
        "Start it by hand when you want a check. It is never on a schedule.",
    ),
)

NOISE_CLEANER: Final = Template(
    key="noise_cleaner",
    name="Noise cleaner",
    tagline="Finds duplicates and noise across your integrations, so you don't have to",
    description=(
        "Looks for open incidents that say the same thing (the same attack reported by several "
        "programs or from many addresses), old quiet ones nothing has touched for days, and ones "
        "the AI is sure are noise. It suggests dismissing, resolving or marking each, and never "
        "touches anything serious. You apply a suggestion with one press and can take it back; "
        "if you let the agents do the surest of it themselves under Settings > Agents, it says "
        "what it did, and that can be taken back too."
    ),
    icon="sparkles",
    brief=(
        "You tidy the incident list. You are given candidates for tidying, each with a key. "
        "Say whether each is really noise or hides something worth the owner's attention. Name "
        'in "rejects" the key of any candidate that should be left alone, and explain in a '
        "finding why. Never invent a key."
    ),
    goal="Keep my incident list down to what needs me, and tell me what you tidied.",
    first=(
        Lookup("cleanup_candidates", Args(limit=10)),
        Lookup("noisy_alerts", Args(hours=24, limit=5)),
    ),
    asks=("cleanup_candidates", "incident", "repeated_incidents", "noisy_alerts", "alerts"),
    interval_minutes=360,
    proposes=True,
    needs=("alerts",),
    setup=(
        "Connect your alert sources under Integrations: the more of them report, the more "
        "duplicates there are to find.",
        "It works without an AI, using what AresGate already knows. With one, it also checks "
        "each candidate before suggesting it. Choose the AI under Settings > Agents.",
        "Look at what it suggests on its page. Under Settings > Agents you can let it do the "
        "surest suggestions itself; each is recorded and can be taken back.",
    ),
)

VULNERABILITY_SCANNER: Final = Template(
    key="vulnerability_scanner",
    name="Vulnerability scanner",
    tagline="Reads what your devices' services announce, and what is wrong with it",
    description=(
        "Connects to the web, mail and SSH services of the devices AresGate has seen at home and "
        "reads what each says of itself: an expired or weak certificate, an SSH server that still "
        "speaks protocol 1, a web server that asks for a password in the clear, the software and "
        "version a service announces. It logs in to nothing and changes nothing, tests only your "
        "own network, only when you start it and only once you have allowed it on the agent."
    ),
    icon="shield-alert",
    brief=(
        "You look for vulnerabilities on the home network. You are given what the services of "
        "the devices announce about themselves and what is wrong with each. Say which matter "
        "most and why, and what to do about each in plain words: update, renew, switch to the "
        "encrypted address, turn it off. For a software version, say what to look up and where. "
        "Never suggest attacking anything and never invent a weakness that was not reported."
    ),
    goal="Tell me which of my devices need an update or a fix first, and how.",
    first=(Lookup("read_services"), Lookup("scan_exposure")),
    asks=("device", "new_devices"),
    interval_minutes=None,
    active=True,
    needs=("ai", "devices"),
    setup=(
        "Connect OPNsense or ntopng under Integrations, so that AresGate knows which devices are "
        "on the network. It reads only those.",
        "Edit the agent and allow it to test your network: it does nothing until you do. It "
        "connects to a short list of ports, reads a certificate, a greeting or a web server's "
        "headers, and logs in to nothing.",
        "Start it by hand when you want a check, for example after adding a device. It is never "
        "on a schedule.",
    ),
)
ROGUE_DEVICE_WATCH: Final = Template(
    key="rogue_device_watch",
    name="Rogue device watch",
    tagline="Notices a device that joined your network and should not have",
    description=(
        "Looks at the devices that appeared on your network for the first time lately and at "
        "what the alerts say about them, and tells you which to check: one with no name, one "
        "from a maker you do not own anything from, one that was loud the moment it joined."
    ),
    icon="wifi",
    brief=(
        "You watch for devices that should not be on the home network. Look at the devices that "
        "appeared recently, and whether they appear in any incident or alert. Say which the "
        "owner should check, and how to tell whether it is theirs: ask who in the house owns "
        "it, look at the router's list, check the maker. Do not assume a new device is hostile; "
        "most are a phone or a guest."
    ),
    goal="Tell me about any new device I should check, and ignore the ones that look like phones.",
    first=(
        Lookup("new_devices", Args(hours=72, limit=10)),
        Lookup("open_incidents", Args(limit=5)),
    ),
    asks=("new_devices", "device", "open_incidents", "incident", "alerts"),
    interval_minutes=120,
    needs=("ai", "devices"),
    setup=(
        "Connect OPNsense or ntopng under Integrations: they tell AresGate which devices are on "
        "the network, and when each first appeared.",
        CHOOSE_AI,
        "Start it once by hand. Devices already there are not new, so it reports only what joins "
        "from then on.",
    ),
)
FIREWALL_REVIEWER: Final = Template(
    key="firewall_reviewer",
    name="Firewall reviewer",
    tagline="Reads what your firewall turned away, and what it says about your setup",
    description=(
        "Looks at the ports and the addresses the firewall refused most, and at the alerts that "
        "repeat, and tells you what it suggests: a service someone keeps trying to reach, a "
        "rule that is noisy, an address worth blocking for good. It only reads. It cannot "
        "change a rule."
    ),
    icon="flame",
    brief=(
        "You review what the home firewall has turned away. Look at the ports that were targeted "
        "most, the addresses refused most and the alerts that repeat. Say what it tells the "
        "owner about their network and what, if anything, to change in the firewall. You cannot "
        "change a rule yourself, so never say that you did."
    ),
    goal="Tell me what the firewall is telling me, and one thing to change if there is one.",
    first=(
        Lookup("targeted_ports", Args(hours=24, limit=5)),
        Lookup("blocked_sources", Args(hours=24, limit=5)),
        Lookup("noisy_alerts", Args(hours=24, limit=5)),
    ),
    asks=("targeted_ports", "blocked_sources", "noisy_alerts", "alerts", "reputation"),
    interval_minutes=720,
    needs=("ai", "firewall"),
    setup=(
        "Connect OPNsense under Integrations and turn on its firewall log: this agent reads "
        "what the firewall refused.",
        CHOOSE_AI,
    ),
)
PENETRATION_TEST_PLANNER: Final = Template(
    key="penetration_test_planner",
    name="Penetration test planner",
    tagline="Thinks like an attacker about your network, so you can close the way in first",
    description=(
        "Reads what the other agents found, what has been probing you and which services are "
        "open, and sets out how an attacker would go about it: the most likely way in, what they "
        "would reach next and what to close first. It plans and explains; it never attacks "
        "anything and sends nothing to your network."
    ),
    icon="swords",
    brief=(
        "You plan a penetration test of the home network on paper, as a defender. You are given "
        "what the other agents reported and what has been probing the network. Describe the "
        "most likely ways in, in order, what an attacker would reach after each, and what the "
        "owner should close first to cut that path. Use only what you were given; mark a guess "
        "as a guess. Never give instructions for breaking into anything: say what to defend, "
        "not how to attack."
    ),
    goal="Show me the way in an attacker would most likely take, and what to close first.",
    first=(
        Lookup("agent_findings", Args(limit=10)),
        Lookup("targeted_ports", Args(hours=72, limit=5)),
        Lookup("open_incidents", Args(limit=5)),
    ),
    asks=(
        "agent_findings",
        "targeted_ports",
        "open_incidents",
        "incident",
        "device",
        "blocked_sources",
        "new_devices",
    ),
    interval_minutes=None,
    needs=("ai", "alerts", "agents"),
    setup=(
        "Make a Vulnerability scanner or an Exposure scanner agent and run it: this agent builds "
        "on what they found, and has little to say without it.",
        "Connect at least one source of alerts under Integrations, so that it knows what has "
        "been probing you.",
        "Choose the AI the agents ask under Settings > Agents, and start it by hand after a scan.",
    ),
)

TEMPLATES: Final[tuple[Template, ...]] = (
    THREAT_HUNTER,
    INTELLIGENCE_ANALYST,
    HEALTH_WATCH,
    NOISE_CLEANER,
    EXPOSURE_SCANNER,
    VULNERABILITY_SCANNER,
    ROGUE_DEVICE_WATCH,
    FIREWALL_REVIEWER,
    PENETRATION_TEST_PLANNER,
)


def template(key: str) -> Template | None:
    return next((item for item in TEMPLATES if item.key == key), None)
