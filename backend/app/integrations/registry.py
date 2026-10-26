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

from pydantic import BaseModel, ConfigDict, Field

MAX_TEXT = 128
API_KEY = "API key"


class FieldKind(StrEnum):
    TEXT = "text"
    # Written and never read back: it goes to the credential store, not the database row.
    SECRET = "secret"  # noqa: S105  # nosec B105: a kind of field, not a password
    NUMBER = "number"
    CHOICE = "choice"


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


class IntegrationDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    # What it gives AresGate to work with.
    provides: str
    # The kind of thing it is, as one word ("firewall"): the web app picks the picture.
    icon: str
    docs_url: str
    # How to get what the fields ask for, in the product's own terms.
    setup: tuple[str, ...]
    connections: tuple[ConnectionDef, ...]

    def connection(self, key: str) -> ConnectionDef | None:
        return next((item for item in self.connections if item.key == key), None)


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
    docs_url="https://docs.opnsense.org/development/how-tos/api.html",
    setup=(
        "In OPNsense, open System, Access, Users and make a user for AresGate, or edit one.",
        "Give that user only the privileges to view what AresGate collects: diagnostics, "
        "interfaces, gateways, the firewall log, intrusion detection and the services you run. "
        "OPNsense applies the same permissions to the API as to its web pages, and a key can do "
        "whatever its user can.",
        "Under API keys on the user, click +. OPNsense downloads apikey.txt with the key and the "
        "secret. The secret is shown only once, so make a new key if it is lost.",
        "Enter the address you open OPNsense at, then paste the key and the secret. Testing the "
        "connection then finds which services are installed, such as Suricata, CrowdSec, OpenVPN "
        "and WireGuard, and shows them under Services. Switch off any you don't want read.",
        "Zenarmor has an API of its own, on a port of its own, that takes a key made in "
        "Zenconsole: register the firewall there, enable the API and make a key. Add it under "
        "Zenarmor if you use it.",
    ),
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
    docs_url="https://www.ntop.org/guides/ntopng/api/rest/api_v2.html",
    setup=(
        "In ntopng, edit the user AresGate will use and generate its User Authentication Token. "
        "ntopng's authentication guide shows where.",
        "Choose Token below and paste it, or choose Username and password to use HTTP basic "
        "authentication instead.",
        "ntopng answers a login it refuses by redirecting to its login page, and AresGate doesn't "
        "follow redirects, so a refused login shows up as a redirect.",
        "The interface ID is the ifid in ntopng's addresses. The first interface is usually 0.",
        "The user must be allowed to see alerts, which AresGate reads along with the hosts and the "
        "interface's traffic.",
    ),
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
                    label="Interface ID",
                    kind=FieldKind.NUMBER,
                    default=0,
                    minimum=0,
                    maximum=999,
                    help="The ifid of the interface to read.",
                ),
            ),
        ),
    ),
)

WAZUH = IntegrationDef(
    key="wazuh",
    name="Wazuh",
    provides=("Security alerts from the indexer, and the health of the agents from the manager."),
    icon="alerts",
    docs_url="https://documentation.wazuh.com/current/user-manual/api/getting-started.html",
    setup=(
        "Manager: in the Wazuh dashboard, create an API user for AresGate (Server management, "
        "Security, Users) and give it a read-only role, rather than using the administrator. "
        "The API listens on port 55000 over HTTPS, with a self-signed certificate until you "
        "replace it.",
        "Indexer: create a user that may read the wazuh-alerts-* indices, rather than using "
        "admin. It listens on port 9200 over HTTPS and uses basic authentication, also with a "
        "self-signed certificate in a default install.",
        "A self-signed certificate is trusted by pasting the certificate authority that signed "
        "it, or by pinning its fingerprint, under Certificate.",
    ),
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
        ),
    ),
)

CROWDSEC = IntegrationDef(
    key="crowdsec",
    name="CrowdSec",
    provides="The ban decisions CrowdSec has made, from its local API.",
    icon="threats",
    docs_url="https://docs.crowdsec.net/docs/local_api/authentication/",
    setup=(
        "Where CrowdSec runs, run cscli bouncers add aresgate. It prints an API key once. A "
        "bouncer's key can only read decisions.",
        "The local API listens on 127.0.0.1:8080 unless api.server.listen_uri in CrowdSec's "
        "config.yaml says otherwise. Make it listen on an address AresGate can reach.",
        "The local API speaks plain HTTP unless you set up TLS for it. AresGate accepts http:// "
        "here, but anyone on the network path can read the key.",
    ),
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

INTEGRATIONS: Mapping[str, IntegrationDef] = {
    item.key: item for item in (OPNSENSE, NTOPNG, WAZUH, CROWDSEC)
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


class _Invalid(Exception):
    """What is wrong with one field's value, in words for whoever filled it in."""


def _accept(item: FieldDef, given: Mapping[str, str | int | None]) -> str | int:
    """The field's value tidied, from what was given or else its default. Raises ``_Invalid``."""
    value = given.get(item.key)
    if value is None or (isinstance(value, str) and not value.strip()):
        value = item.default
    if value is None:
        raise _Invalid("Enter a value.")
    problem = _check(item, value)
    if problem:
        raise _Invalid(problem)
    return int(value) if item.kind is FieldKind.NUMBER else str(value).strip()


def _check(item: FieldDef, value: str | int) -> str | None:
    text = str(value).strip()
    if item.kind is FieldKind.NUMBER:
        whole = text.isascii() and text.isdigit()
        if not whole or not item.minimum <= int(text) <= item.maximum:
            return f"Enter a whole number from {item.minimum} to {item.maximum}."
    elif item.kind is FieldKind.CHOICE:
        if text not in {choice.value for choice in item.choices}:
            return "Choose one of the options."
    elif len(text) > MAX_TEXT or not text.isprintable():
        return f"Use at most {MAX_TEXT} characters, and no control characters."
    return None
