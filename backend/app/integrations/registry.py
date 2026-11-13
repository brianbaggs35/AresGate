"""Which integrations exist, what each needs to connect and where to read how, taken from the
products' own documentation.

An integration is made of one or more connections: OPNsense, ntopng and CrowdSec have one API
each, while Wazuh has two (the manager's API and the indexer). Each connection has its own
address, its own way of checking the certificate and its own secrets. The web app builds the
settings page from these definitions, so adding an integration (Suricata and others later) means
adding one here, and a probe in ``probes``.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.integrations import guides
from app.integrations.guides import Guide

MAX_TEXT = 128
NETWORK_MONITORING = "Network monitoring"
API_KEY = "API key"
# The most a lookup that allows several can have chosen: more than any home has interfaces.
MAX_CHOSEN = 16


class FieldKind(StrEnum):
    TEXT = "text"
    # Written and never read back: it goes to the credential store, not the database row.
    SECRET = "secret"  # noqa: S105  # nosec B105: a kind of field, not a password
    NUMBER = "number"
    CHOICE = "choice"
    # A whole number the system itself lists, such as ntopng's interfaces, which the web app asks
    # for with a button (``FieldDef.action``) and offers as a list. It is kept like a number, or,
    # if more than one can be chosen (``FieldDef.multiple``), as the numbers joined by commas.
    LOOKUP = "lookup"


class ModuleState(StrEnum):
    """What testing a connection found out about a module."""

    RUNNING = "running"
    STOPPED = "stopped"
    # There, but it didn't say whether it is running.
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    # The key's user isn't allowed to see it.
    NO_ACCESS = "no_access"
    UNKNOWN = "unknown"

    @property
    def present(self) -> bool:
        return self in (ModuleState.RUNNING, ModuleState.STOPPED, ModuleState.INSTALLED)


class Choice(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    label: str


class Entry(BaseModel):
    """One thing a system lists when asked, such as one of ntopng's interfaces."""

    model_config = ConfigDict(frozen=True)

    # What is kept when it is chosen.
    value: str
    label: str
    # What else is known of it, in a few words.
    detail: str = ""
    # Nothing has passed through it yet.
    quiet: bool = False
    # It only carries a machine's traffic to itself, which normally has nothing worth reading.
    loopback: bool = False


class Condition(BaseModel):
    """The field only applies while another field has this value."""

    model_config = ConfigDict(frozen=True)

    field: str
    value: str


class FieldDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    kind: FieldKind
    help: str = ""
    placeholder: str = ""
    default: str | int | None = None
    choices: tuple[Choice, ...] = ()
    minimum: int = 0
    maximum: int = 65535
    only_if: Condition | None = None
    # For a lookup: the button that asks the system for its list ("Fetch interfaces").
    action: str = ""
    # For a lookup: more than one can be chosen. They are kept as numbers joined by commas
    # (``0,1``), lowest first, and ``chosen_numbers`` reads them back.
    multiple: bool = False
    # What the owner must know before choosing, shown as a warning beside the field, such as what
    # a free access level is not allowed to be used for. Empty when there is nothing to warn of.
    caution: str = ""


class ModuleDef(BaseModel):
    """A service that runs on the system a connection reaches, and that AresGate can read through
    it, such as Suricata on OPNsense. Testing the connection finds out which are there."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    summary: str
    # A read-only request that shows whether it is installed and running; empty for what the
    # connection's own test already answers.
    path: str = Field(default="", exclude=True)


class ConnectionDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    summary: str
    # What an address looks like, shown as the hint in the address field.
    url_example: str
    # Whether plain http:// is accepted, because the product speaks it by default. The web app
    # warns that what is sent can be read on the network.
    allow_http: bool
    fields: tuple[FieldDef, ...]
    # Left out when the integration doesn't use it (not everyone runs Zenarmor).
    optional: bool = False
    modules: tuple[ModuleDef, ...] = ()
    # What the product's documentation says about this connection's certificate that someone
    # choosing how to trust it needs to know, shown beside that choice. Left empty when the
    # usual advice is all there is.
    certificate_note: str = ""
    # The address the connection always uses, for a service that has one for everyone. The form
    # doesn't ask for it, and whatever is sent in its place is replaced by this one, so that a
    # key is only ever sent to the service it belongs to.
    address: str = ""
    # Whether the service is on the internet rather than the home network. Its address is then
    # checked against the internet's addresses, and never against the home network's. Its
    # certificate is checked by the certificates this computer trusts, as any site's is, so there
    # is none to look up, pin or paste.
    internet: bool = False

    @model_validator(mode="after")
    def _internet_is_its_own_address(self) -> Self:
        """A service on the internet is reached at its own https address and nowhere else, so a
        definition that gives it plain http, or no address, is refused when the app starts."""
        if self.internet and (self.allow_http or not self.address.startswith("https://")):
            raise ValueError("A service on the internet needs its own https address.")
        return self


class IntegrationDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    # What it gives AresGate to work with.
    provides: str
    # The kind of thing it is, as one word ("firewall"): the web app picks the picture.
    icon: str
    # What family of integration it belongs to, shown on its card (such as "Threat intelligence").
    # Empty when it belongs to none.
    category: str = ""
    docs_url: str
    # How to get what the fields ask for, step by step, in the product's own terms.
    guide: Guide
    connections: tuple[ConnectionDef, ...]

    def connection(self, key: str) -> ConnectionDef | None:
        return next((item for item in self.connections if item.key == key), None)

    @property
    def internet_only(self) -> bool:
        """Whether every connection is on the internet, so no certificate on the home network is
        there to look up."""
        return all(item.internet for item in self.connections)


OPNSENSE_MODULES = (
    ModuleDef(
        key="firewall",
        label="Firewall and system",
        summary="Health, interfaces and traffic, gateways, the firewall log, ARP and DHCP.",
    ),
    ModuleDef(
        key="suricata",
        label="Suricata",
        summary="Intrusion detection: whether it runs, and its alerts.",
        path="/api/ids/service/status",
    ),
    ModuleDef(
        key="crowdsec",
        label="CrowdSec",
        summary="The CrowdSec plugin: its alerts and the decisions it has made.",
        path="/api/crowdsec/service/status",
    ),
    ModuleDef(
        key="openvpn",
        label="OpenVPN",
        summary="Connected clients and routes.",
        path="/api/openvpn/service/search_sessions",
    ),
    ModuleDef(
        key="wireguard",
        label="WireGuard",
        summary="Whether the tunnels are up.",
        path="/api/wireguard/service/status",
    ),
    ModuleDef(
        key="ipsec",
        label="IPsec",
        summary="Tunnel sessions.",
        path="/api/ipsec/service/status",
    ),
    ModuleDef(
        key="unbound",
        label="Unbound DNS",
        summary="DNS service state and statistics.",
        path="/api/unbound/service/status",
    ),
    ModuleDef(
        key="dnsmasq",
        label="Dnsmasq",
        summary="DHCP leases and DNS.",
        path="/api/dnsmasq/service/status",
    ),
    ModuleDef(
        key="kea",
        label="Kea DHCP",
        summary="DHCP leases.",
        path="/api/kea/service/status",
    ),
    ModuleDef(
        key="ntopng",
        label="ntopng plugin",
        summary="Whether ntopng runs on the firewall.",
        path="/api/ntopng/service/status",
    ),
    ModuleDef(
        key="wazuhagent",
        label="Wazuh agent",
        summary="Whether the firewall's Wazuh agent runs.",
        path="/api/wazuhagent/service/status",
    ),
)

OPNSENSE = IntegrationDef(
    key="opnsense",
    name="OPNsense",
    provides=(
        "The firewall's health, interfaces and traffic, gateways, firewall log, and ARP and DHCP "
        "tables, and the services that run on it: Suricata, CrowdSec, OpenVPN, Zenarmor and more."
    ),
    icon="firewall",
    category=NETWORK_MONITORING,
    docs_url="https://docs.opnsense.org/development/how-tos/api.html",
    guide=guides.OPNSENSE,
    connections=(
        ConnectionDef(
            key="api",
            label="OPNsense API",
            summary="OPNsense's REST API, with HTTP basic authentication.",
            url_example="https://192.168.1.1",
            allow_http=False,
            fields=(
                FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),
                FieldDef(key="api_secret", label="API secret", kind=FieldKind.SECRET),
            ),
            modules=OPNSENSE_MODULES,
        ),
        ConnectionDef(
            key="zenarmor",
            label="Zenarmor API",
            summary=(
                "Zenarmor's own API: its address and port are the ones set in Zenconsole, and "
                "its key is sent as the user name of HTTP basic authentication."
            ),
            url_example="https://192.168.1.1:8090",
            allow_http=False,
            optional=True,
            fields=(
                FieldDef(
                    key="user",
                    label="API user",
                    kind=FieldKind.TEXT,
                    help="The user name that Zenarmor's API asks every request to name.",
                ),
                FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),
            ),
        ),
    ),
)

NTOPNG = IntegrationDef(
    key="ntopng",
    name="ntopng",
    provides=(
        "Live traffic on the interface ntopng watches: how much each host sends and receives, the "
        "devices it sees and its alerts."
    ),
    icon="traffic",
    category=NETWORK_MONITORING,
    docs_url="https://www.ntop.org/guides/ntopng/api/rest/api_v2.html",
    guide=guides.NTOPNG,
    connections=(
        ConnectionDef(
            key="api",
            label="REST API",
            summary="ntopng's REST API (version 2), on the port its web interface uses.",
            url_example="http://192.168.1.2:3000",
            allow_http=True,
            fields=(
                FieldDef(
                    key="auth",
                    label="Sign in with",
                    kind=FieldKind.CHOICE,
                    default="token",
                    choices=(
                        Choice(value="token", label="Authentication token"),
                        Choice(value="basic", label="Username and password"),
                    ),
                ),
                FieldDef(
                    key="token",
                    label="Authentication token",
                    kind=FieldKind.SECRET,
                    only_if=Condition(field="auth", value="token"),
                ),
                FieldDef(
                    key="username",
                    label="Username",
                    kind=FieldKind.TEXT,
                    only_if=Condition(field="auth", value="basic"),
                ),
                FieldDef(
                    key="password",
                    label="Password",
                    kind=FieldKind.SECRET,
                    only_if=Condition(field="auth", value="basic"),
                ),
                FieldDef(
                    key="interface_id",
                    label="Interfaces",
                    kind=FieldKind.LOOKUP,
                    # ntopng numbers its interfaces itself, with gaps and not always from 0, so
                    # there is no number that can be assumed: empty reads every interface it lists
                    # but the loopback.
                    default="",
                    minimum=0,
                    maximum=999,
                    help=(
                        "The interfaces ntopng watches that AresGate reads (their ifid). Leave it "
                        "empty to read every one except the loopback."
                    ),
                    action="Fetch interfaces",
                    multiple=True,
                ),
            ),
        ),
    ),
)

# Wazuh's page on Let's Encrypt covers the dashboard alone, and its pages call the API's default
# certificate self-signed and name root-ca.pem as the authority that signs the others, so a
# certificate from Let's Encrypt on the dashboard is not what these two answer with.
WAZUH_API_CERTIFICATE = (
    "Wazuh's instructions for Let's Encrypt are for the dashboard only. The manager's API has a "
    "certificate of its own, self-signed unless you replaced it, so a Let's Encrypt certificate "
    "on the dashboard isn't what answers here. Pin the API's certificate."
)
WAZUH_INDEXER_CERTIFICATE = (
    "Wazuh's instructions for Let's Encrypt are for the dashboard only. The indexer answers with "
    "a certificate that Wazuh's certificate tool made, signed by its own authority (root-ca.pem), "
    "unless you replaced it, so a Let's Encrypt certificate on the dashboard isn't what answers "
    "here. Paste root-ca.pem as the authority, or pin the certificate."
)

WAZUH = IntegrationDef(
    key="wazuh",
    name="Wazuh",
    provides=("Security alerts from the indexer, and the health of the agents from the manager."),
    icon="alerts",
    category=NETWORK_MONITORING,
    docs_url="https://documentation.wazuh.com/current/user-manual/api/getting-started.html",
    guide=guides.WAZUH,
    connections=(
        ConnectionDef(
            key="manager",
            label="Manager API",
            summary="The Wazuh manager's API: the agents and whether they are reporting.",
            url_example="https://192.168.1.3:55000",
            allow_http=False,
            fields=(
                FieldDef(key="username", label="Username", kind=FieldKind.TEXT),
                FieldDef(key="password", label="Password", kind=FieldKind.SECRET),
            ),
            certificate_note=WAZUH_API_CERTIFICATE,
        ),
        ConnectionDef(
            key="indexer",
            label="Indexer",
            summary="The Wazuh indexer, which keeps the alerts for searching.",
            url_example="https://192.168.1.3:9200",
            allow_http=False,
            fields=(
                FieldDef(key="username", label="Username", kind=FieldKind.TEXT),
                FieldDef(key="password", label="Password", kind=FieldKind.SECRET),
            ),
            certificate_note=WAZUH_INDEXER_CERTIFICATE,
        ),
    ),
)

CROWDSEC = IntegrationDef(
    key="crowdsec",
    name="CrowdSec",
    provides="The ban decisions CrowdSec has made, from its local API.",
    icon="threats",
    category=NETWORK_MONITORING,
    docs_url="https://docs.crowdsec.net/docs/local_api/authentication/",
    guide=guides.CROWDSEC,
    connections=(
        ConnectionDef(
            key="lapi",
            label="Local API",
            summary="CrowdSec's local API, with a bouncer's API key.",
            url_example="http://192.168.1.4:8080",
            allow_http=True,
            fields=(FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),),
        ),
    ),
)

THREAT_INTELLIGENCE = "Threat intelligence"
# What the owner is told beside the access level. The free public API's terms forbid business and
# commercial use, so the choice has to be made knowingly. Lookups are spaced to the free limits.
TIER_CAUTION = (
    "Free and premium differ. The free public API allows 4 lookups a minute and 500 a day, and it "
    "must not be used in business workflows, commercial products or services. Premium's limits "
    "depend on your plan. Pick the level your key has: on free, AresGate spaces its lookups to "
    "the limits. VirusTotal also shares each address it is asked about with its community, so "
    "only addresses on the internet are sent."
)

VIRUSTOTAL = IntegrationDef(
    key="virustotal",
    name="VirusTotal",
    provides=(
        "How many security vendors flag each internet address, and who owns it, so that the AI "
        "reads an incident with that in mind."
    ),
    icon="threats",
    category=THREAT_INTELLIGENCE,
    docs_url="https://docs.virustotal.com/reference/overview",
    guide=guides.VIRUSTOTAL,
    connections=(
        ConnectionDef(
            key="api",
            label="VirusTotal API",
            summary="VirusTotal's API, with the API key from your account. Its address is fixed.",
            url_example="https://www.virustotal.com",
            address="https://www.virustotal.com",
            allow_http=False,
            internet=True,
            fields=(
                FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),
                FieldDef(
                    key="tier",
                    label="Access level",
                    kind=FieldKind.CHOICE,
                    default="free",
                    choices=(
                        Choice(value="free", label="Free public API"),
                        Choice(value="premium", label="Premium API"),
                    ),
                    caution=TIER_CAUTION,
                ),
            ),
        ),
    ),
)

PACE_NOTE = (
    "OTX publishes no limit on requests, so AresGate paces itself. Gentle asks about one new "
    "address every 90 seconds, balanced every 30 and fast every 10, each with a cap on a day's "
    "lookups. If OTX ever answers that it is being asked too much, lookups stop for five minutes."
)

ALIENVAULT_OTX = IntegrationDef(
    key="otx",
    name="AlienVault OTX",
    provides=(
        "Which threat reports from the OTX community name each internet address in an incident, "
        "and what they say it is part of, so that the AI weighs that when it classifies."
    ),
    icon="threats",
    category=THREAT_INTELLIGENCE,
    docs_url="https://otx.alienvault.com/assets/static/external_api.html",
    guide=guides.OTX,
    connections=(
        ConnectionDef(
            key="api",
            label="OTX API",
            summary="AlienVault OTX's API, with the key from your account. Its address is fixed.",
            url_example="https://otx.alienvault.com",
            address="https://otx.alienvault.com",
            allow_http=False,
            internet=True,
            fields=(
                FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),
                FieldDef(
                    key="pace",
                    label="Lookup pace",
                    kind=FieldKind.CHOICE,
                    default="balanced",
                    choices=(
                        Choice(value="gentle", label="Gentle"),
                        Choice(value="balanced", label="Balanced"),
                        Choice(value="fast", label="Fast"),
                    ),
                    caution=PACE_NOTE,
                ),
            ),
        ),
    ),
)

GREYNOISE_NOTE = (
    "GreyNoise is asked about addresses on the internet and nothing else, and only IPv4 ones: its "
    "Community API takes no other. The Community API allows 10 lookups a day without an account, "
    "and 50 searches a week with a free account's key, which the GreyNoise Visualizer shares, so "
    "AresGate asks about a new address every few hours and leaves some of the week for you. "
    "Only an account made with a business email is given an API key. A subscription's limits "
    "aren't published, so AresGate asks gently. If GreyNoise answers that the limit is reached, "
    "lookups stop for an hour."
)

GREYNOISE = IntegrationDef(
    key="greynoise",
    name="GreyNoise",
    provides=(
        "Whether an address on the internet is one of the thousands that scan every address, "
        "or belongs to a common business service, so that the AI can tell background noise "
        "from an attack that was aimed at you."
    ),
    icon="threats",
    category=THREAT_INTELLIGENCE,
    docs_url="https://docs.greynoise.io/",
    guide=guides.GREYNOISE,
    connections=(
        ConnectionDef(
            key="api",
            label="GreyNoise API",
            summary="GreyNoise's API, with the key from your account. Its address is fixed.",
            url_example="https://api.greynoise.io",
            address="https://api.greynoise.io",
            allow_http=False,
            internet=True,
            fields=(
                FieldDef(
                    key="access",
                    label="Account",
                    kind=FieldKind.CHOICE,
                    default="key",
                    choices=(
                        Choice(value="key", label="An account with an API key"),
                        Choice(value="none", label="No account"),
                    ),
                    caution=GREYNOISE_NOTE,
                ),
                FieldDef(
                    key="plan",
                    label="Plan",
                    kind=FieldKind.CHOICE,
                    default="free",
                    choices=(
                        Choice(value="free", label="Free"),
                        Choice(value="subscription", label="Standard, Advanced or Elite"),
                    ),
                    only_if=Condition(field="access", value="key"),
                ),
                FieldDef(
                    key="api_key",
                    label=API_KEY,
                    kind=FieldKind.SECRET,
                    only_if=Condition(field="access", value="key"),
                ),
            ),
        ),
    ),
)

NVD_NOTE = (
    "NVD is asked about CVEs only: the identifiers that the incidents name, and nothing else is "
    "sent, no address and nothing of your network. A key is optional. Without one NVD allows 5 "
    "requests in 30 seconds, and with one 50, and AresGate asks about one CVE every few seconds "
    "at most, so the free key is more than enough. A key belongs to one person or application "
    "and is not to be shared."
)

NVD = IntegrationDef(
    key="nvd",
    name="NIST NVD",
    provides=(
        "What the National Vulnerability Database says of each CVE an incident names: its CVSS "
        "score and rating, the weakness behind it, and whether CISA lists it as exploited in the "
        "wild, so that the AI weighs how dangerous it is when it classifies."
    ),
    icon="threats",
    category=THREAT_INTELLIGENCE,
    docs_url="https://nvd.nist.gov/developers/start-here",
    guide=guides.NVD,
    connections=(
        ConnectionDef(
            key="api",
            label="NVD API",
            summary="The National Vulnerability Database's CVE API. Its address is fixed.",
            url_example="https://services.nvd.nist.gov",
            address="https://services.nvd.nist.gov",
            allow_http=False,
            internet=True,
            fields=(
                FieldDef(
                    key="access",
                    label="API key",
                    kind=FieldKind.CHOICE,
                    default="key",
                    choices=(
                        Choice(value="key", label="Ask with an API key"),
                        Choice(value="none", label="Ask without a key"),
                    ),
                    caution=NVD_NOTE,
                ),
                FieldDef(
                    key="api_key",
                    label=API_KEY,
                    kind=FieldKind.SECRET,
                    only_if=Condition(field="access", value="key"),
                ),
            ),
        ),
    ),
)

DEVICE_INTELLIGENCE = "Device intelligence"
# Fingerbank's free key is understood to allow 600 requests an hour (the maintainer's figure; the
# pages read give none), and AresGate stays inside that. The API
# itself caps every key at 250 a minute and answers 429 above it. Fingerbank also keeps what it is
# sent to improve its matching, which is why what is sent is only a hardware address.
FINGERBANK_NOTE = (
    "Fingerbank is asked about a device's hardware address and nothing else: not its name, its "
    "traffic or its IP address. Devices that made up their own hardware address are never sent. "
    "Fingerbank keeps what it is sent to improve its matching, and says it never makes it public "
    "or shares it. The free key is understood to allow 600 requests an hour, and AresGate stays "
    "inside that, waiting when the limit is reached rather than counting it as an error."
)
INCIDENT_DEVICES_NOTE = (
    "Your own devices are always identified. Turn this on to identify devices that appear in "
    "incidents and threats as well, such as the machines on the internet side of the firewall. "
    "It sends their hardware addresses to Fingerbank too."
)

FINGERBANK = IntegrationDef(
    key="fingerbank",
    name="Fingerbank",
    provides=(
        "What each device on the network is, from its hardware address: its make and model, its "
        "operating system and how sure Fingerbank is. It is kept with the device, so every later "
        "connection from the same hardware carries it."
    ),
    icon="devices",
    category=DEVICE_INTELLIGENCE,
    docs_url="https://api.fingerbank.org/api_doc/2.html",
    guide=guides.FINGERBANK,
    connections=(
        ConnectionDef(
            key="api",
            label="Fingerbank API",
            summary="Fingerbank's API, with the key from your account. Its address is fixed.",
            url_example="https://api.fingerbank.org",
            address="https://api.fingerbank.org",
            allow_http=False,
            internet=True,
            fields=(
                FieldDef(key="api_key", label=API_KEY, kind=FieldKind.SECRET),
                FieldDef(
                    key="incident_devices",
                    label="Devices in incidents and threats",
                    kind=FieldKind.CHOICE,
                    default="no",
                    choices=(
                        Choice(value="no", label="Only my own devices"),
                        Choice(value="yes", label="Also devices in incidents and threats"),
                    ),
                    help=INCIDENT_DEVICES_NOTE,
                    caution=FINGERBANK_NOTE,
                ),
            ),
        ),
    ),
)

INTEGRATIONS: Mapping[str, IntegrationDef] = {
    item.key: item
    for item in (
        OPNSENSE,
        NTOPNG,
        WAZUH,
        CROWDSEC,
        VIRUSTOTAL,
        ALIENVAULT_OTX,
        GREYNOISE,
        NVD,
        FINGERBANK,
    )
}


def credential_name(integration: str, connection: str) -> str:
    """What a connection's secrets are filed under in the credential store."""
    return f"{integration}-{connection}"


class SettingsError(ValueError):
    """Settings that can't be used, with what is wrong with each field."""

    def __init__(self, problems: Mapping[str, str]) -> None:
        super().__init__("; ".join(f"{field}: {message}" for field, message in problems.items()))
        self.problems = dict(problems)


def _applies(item: FieldDef, options: Mapping[str, str | int]) -> bool:
    return item.only_if is None or options.get(item.only_if.field) == item.only_if.value


def active_fields(connection: ConnectionDef, options: Mapping[str, str | int]) -> list[FieldDef]:
    """The fields that apply given the choices made: a field that depends on another is left out
    unless that one has the value it needs."""
    return [item for item in connection.fields if _applies(item, options)]


def clean_options(
    connection: ConnectionDef, given: Mapping[str, str | int | None]
) -> dict[str, str | int]:
    """The settings that aren't secret, checked and trimmed. A missing one takes its default.
    Fields that don't apply are dropped. Raises ``SettingsError`` naming each field that is
    wrong."""
    options: dict[str, str | int] = {}
    problems: dict[str, str] = {}
    for item in connection.fields:
        if item.kind is FieldKind.SECRET or not _applies(item, options):
            continue
        try:
            options[item.key] = _accept(item, given)
        except _Invalid as invalid:
            problems[item.key] = str(invalid)
    if problems:
        raise SettingsError(problems)
    return options


# The kinds of field that hold a whole number.
_WHOLE = (FieldKind.NUMBER, FieldKind.LOOKUP)


class _Invalid(Exception):
    """What is wrong with one field's value, in words for whoever filled it in."""


def _accept(item: FieldDef, given: Mapping[str, str | int | None]) -> str | int:
    """The field's value tidied, from what was given or else its default. Raises ``_Invalid``."""
    value = given.get(item.key)
    if value is None or (isinstance(value, str) and not value.strip()):
        value = item.default
    if value is None:
        raise _Invalid("Enter a value.")
    if item.kind is FieldKind.LOOKUP and item.multiple:
        return ",".join(str(number) for number in _several(item, value))
    problem = _check(item, value)
    if problem:
        raise _Invalid(problem)
    return int(value) if item.kind in _WHOLE else str(value).strip()


def chosen_numbers(value: str | int) -> list[int]:
    """The whole numbers a lookup that allows several holds, lowest first, from what was saved:
    ``"0,1"``, or a single number such as an interface chosen before several could be. What isn't
    a number is left out."""
    parts = (part.strip() for part in str(value).split(","))
    return sorted({int(part) for part in parts if part.isascii() and part.isdigit()})


def _several(item: FieldDef, value: str | int) -> list[int]:
    """The numbers chosen, each checked, without repeats and lowest first. Raises ``_Invalid``."""
    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    for part in parts:
        if not (part.isascii() and part.isdigit() and item.minimum <= int(part) <= item.maximum):
            raise _Invalid(
                "Choose from the list, or enter whole numbers from "
                f"{item.minimum} to {item.maximum} separated by commas."
            )
    numbers = chosen_numbers(",".join(parts))
    if len(numbers) > MAX_CHOSEN:
        raise _Invalid(f"Choose at most {MAX_CHOSEN}.")
    return numbers


def _check(item: FieldDef, value: str | int) -> str | None:
    text = str(value).strip()
    if item.kind in _WHOLE:
        whole = text.isascii() and text.isdigit()
        if not whole or not item.minimum <= int(text) <= item.maximum:
            return f"Enter a whole number from {item.minimum} to {item.maximum}."
    elif item.kind is FieldKind.CHOICE:
        if text not in {choice.value for choice in item.choices}:
            return "Choose one of the options."
    elif len(text) > MAX_TEXT or not text.isprintable():
        return f"Use at most {MAX_TEXT} characters, and no control characters."
    return None
