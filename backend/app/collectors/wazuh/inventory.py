"""What Wazuh's agents say is on their machines: the system, the network interfaces, the ports
that listen and the software installed.

Each agent's inventory module (syscollector) reports to the manager, which writes it to the
indexer's ``wazuh-states-inventory-*`` indices, one document for each fact: ``system`` (the
operating system, its version, the host name and the architecture), ``interfaces`` (an interface's
name, its ``host.mac`` and its state), ``networks`` (the addresses of an interface, ``network.ip``
and ``interface.name``), ``ports`` and ``packages``. The manager's own inventory endpoints are
going away in Wazuh 5, in favour of these indices (wazuh/wazuh issue 31299), so this reads them.
See ``indexer.py`` for where the field names come from.

Three things are made of it:

- the machines, with their operating system, ports and software, for the analyst to be asked
  about (``app/hostinfo``);
- the devices: an interface with a hardware address is a device on the Devices page, with every
  address the interface has and the machine's name, listed as ``inventory`` and never as on the
  network now, since what an agent said an hour ago is not that;
- nothing else: the manager's list of agents (``agents.py``) is still what says which are in
  touch.

What could only be inferred, because no page lists the values: that a port that listens has the
state ``listening`` (and ``LISTEN``), that its local end is ``source.ip`` and ``source.port``,
that an interface that is down has the state ``down``, and which interfaces are not a machine's
own (a bridge or a virtual cable of a container host, see ``VIRTUAL``). A run asks for at most
10,000 documents of each index, so a machine with more than that is not read in full."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final

from app.collectors import traffic
from app.collectors.base import Collector, Context, Outcome
from app.collectors.wazuh import indexer
from app.devices import ways
from app.devices.sighting import NewSighting, mac_address
from app.hostinfo.store import NewPackage, NewPort, NewSystem
from app.integrations import probes

SOURCE = "wazuh"
CONNECTION = "indexer"
PREFIX = "wazuh-states-inventory-"
SYSTEM, INTERFACES, NETWORKS, PACKAGES, PORTS = (
    f"{PREFIX}{name}*" for name in ("system", "interfaces", "networks", "packages", "ports")
)
LISTENING: Final = ("listening", "LISTEN")
# The interfaces of a bridge, a container or a virtual machine host are not the machine, and a
# device for each would fill the Devices page.
VIRTUAL: Final = (
    "lo",
    "docker",
    "br-",
    "veth",
    "virbr",
    "cni",
    "flannel",
    "cali",
    "tun",
    "tap",
    "vmnet",
    "vboxnet",
)
Address = IPv4Address | IPv6Address


class Inventory(Collector):
    key = "wazuh-inventory"
    title = "Inventory"
    summary = (
        "Reads what Wazuh's agents report about their machines every 15 minutes: the operating "
        "system, the ports that listen and the software installed, for the analyst to be asked "
        "about, and the network cards as devices."
    )
    interval = timedelta(minutes=15)
    timeout = timedelta(minutes=3)
    integration = SOURCE
    connection = CONNECTION

    async def collect(self, context: Context) -> Outcome:
        system = await _all(context, SYSTEM)
        interfaces = await _all(context, INTERFACES)
        networks = await _all(context, NETWORKS)
        packages = await _all(context, PACKAGES)
        ports = await _all(
            context,
            PORTS,
            {"bool": {"filter": [{"terms": {"interface.state": list(LISTENING)}}]}},
        )
        known = await context.save(indexer.listed)
        found = machines(
            system.sources, interfaces.sources, networks.sources, packages.sources, ports.sources
        )
        # What isn't read in full can't say a machine is gone.
        await context.record_systems(found, complete=not system.more)
        await context.record_devices(
            sightings(found, interfaces.sources, networks.sources, known, context.now),
            ways.INVENTORY,
        )
        return Outcome(items=len(found))


async def _all(
    context: Context, index: str, query: Mapping[str, object] | None = None
) -> indexer.Page:
    return await indexer.search(
        context, index, {"size": indexer.WINDOW, "query": query or {"match_all": {}}}
    )


def machines(
    system: Sequence[Mapping[str, object]],
    interfaces: Sequence[Mapping[str, object]],
    networks: Sequence[Mapping[str, object]],
    packages: Sequence[Mapping[str, object]],
    ports: Sequence[Mapping[str, object]],
) -> list[NewSystem]:
    """The machines the documents are about, in the order their agents first appear: a document
    that names no agent is left out, and a machine is as complete as what was reported of it."""
    names: dict[str, str] = {}
    for documents in (system, interfaces, networks, packages, ports):
        for document in documents:
            agent, name = indexer.agent_of(document)
            if agent:
                names[agent] = names.get(agent) or name
    cards, addresses = _cards(interfaces), _addresses(networks)
    described = {agent: document for document in system if (agent := indexer.agent_of(document)[0])}
    return [
        _machine(
            agent,
            name,
            described.get(agent, {}),
            cards.get(agent, {}),
            addresses.get(agent, {}),
            _ports(ports, agent),
            _packages(packages, agent),
        )
        for agent, name in names.items()
    ]


def _machine(
    agent: str,
    name: str,
    document: Mapping[str, object],
    cards: Mapping[str, tuple[str, ...]],
    addresses: Mapping[str, tuple[Address, ...]],
    ports: tuple[NewPort, ...],
    packages: tuple[NewPackage, ...],
) -> NewSystem:
    host = indexer.member(document, "host")
    os = indexer.member(host, "os")
    version = traffic.text(os, "version")
    called = traffic.text(os, "name")
    return NewSystem(
        agent_id=agent,
        name=name or None,
        hostname=traffic.text(host, "hostname") or None,
        os_name=traffic.text(os, "full") or (f"{called} {version}".strip() or None),
        os_version=version or None,
        os_platform=traffic.text(os, "platform") or None,
        architecture=traffic.text(host, "architecture") or None,
        kernel=_kernel(os),
        macs=tuple(dict.fromkeys(mac for found in cards.values() for mac in found)),
        addresses=tuple(
            dict.fromkeys(address for found in addresses.values() for address in found)
        ),
        ports=ports,
        packages=packages,
    )


def _kernel(os: Mapping[str, object]) -> str | None:
    """The kernel's release, such as ``6.8.0-45-generic``: Wazuh 4.14 gives its name, release and
    version, and a pre-release of 5.0 may give it as one text."""
    kernel = os.get("kernel")
    if isinstance(kernel, str):
        return kernel or None
    found = indexer.member(os, "kernel")
    return traffic.text(found, "release") or traffic.text(found, "version") or None


def _own(name: str) -> bool:
    """Whether an interface can be one of a machine's own, which a bridge or a virtual cable
    is not."""
    return bool(name) and not name.lower().startswith(VIRTUAL)


def _cards(interfaces: Sequence[Mapping[str, object]]) -> dict[str, dict[str, tuple[str, ...]]]:
    """The hardware addresses of each agent's interfaces, by interface: those of an interface
    that is not virtual and not down, and that has a hardware address that is a device's."""
    found: dict[str, dict[str, tuple[str, ...]]] = {}
    for document in interfaces:
        agent = indexer.agent_of(document)[0]
        card = indexer.member(document, "interface")
        name = traffic.text(card, "name")
        if not agent or not _own(name) or traffic.text(card, "state").lower() == "down":
            continue
        macs = _macs(indexer.member(document, "host").get("mac"))
        if macs:
            found.setdefault(agent, {})[name] = macs
    return found


def _macs(value: object) -> tuple[str, ...]:
    """The hardware addresses a document gives, as one text or a list, those that are a device's."""
    given = probes.as_array(value) or [value]
    return tuple(
        dict.fromkeys(
            mac
            for item in given
            if isinstance(item, str) and (mac := mac_address(item)) is not None
        )
    )


def _addresses(
    networks: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, tuple[Address, ...]]]:
    """The addresses of each agent's interfaces, by interface, left out when the interface is not
    a machine's own or the address is not one to be found at: the machine itself (loopback), the
    link it is on (link-local) or no address at all."""
    found: dict[str, dict[str, list[Address]]] = {}
    for document in networks:
        agent = indexer.agent_of(document)[0]
        name = traffic.text(indexer.member(document, "interface"), "name")
        address = _address(traffic.text(indexer.member(document, "network"), "ip"))
        if agent and _own(name) and address is not None:
            found.setdefault(agent, {}).setdefault(name, []).append(address)
    return {
        agent: {name: tuple(dict.fromkeys(listed)) for name, listed in by_name.items()}
        for agent, by_name in found.items()
    }


def _address(value: str) -> Address | None:
    try:
        address = ip_address(value.strip().partition("%")[0])
    except ValueError:
        return None
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        return None
    return address


def _ports(documents: Sequence[Mapping[str, object]], agent: str) -> tuple[NewPort, ...]:
    """The ports an agent's machine listens on: each document gives the transport, the local
    address and port, and the program."""
    found: list[NewPort] = []
    for document in documents:
        if indexer.agent_of(document)[0] != agent:
            continue
        local = indexer.member(document, "source")
        number = traffic.number(local, "port")
        try:
            address = ip_address(traffic.text(local, "ip").strip().partition("%")[0])
        except ValueError:
            continue
        if number is None or not 0 < number < 65536:
            continue
        transport = traffic.text(indexer.member(document, "network"), "transport").lower()
        process = traffic.text(indexer.member(document, "process"), "name")
        found.append(NewPort(transport[:8], address, number, process[:128] or None))
    return tuple(found)


def _packages(documents: Sequence[Mapping[str, object]], agent: str) -> tuple[NewPackage, ...]:
    found: list[NewPackage] = []
    for document in documents:
        if indexer.agent_of(document)[0] != agent:
            continue
        package = indexer.member(document, "package")
        name = traffic.text(package, "name")
        if name:
            found.append(
                NewPackage(
                    name[:256],
                    traffic.text(package, "version")[:128],
                    traffic.text(package, "architecture")[:32],
                    traffic.text(package, "type")[:16],
                )
            )
    return tuple(found)


def sightings(
    found: Sequence[NewSystem],
    interfaces: Sequence[Mapping[str, object]],
    networks: Sequence[Mapping[str, object]],
    known: Mapping[str, indexer.Listed],
    now: datetime,
) -> list[NewSighting]:
    """A sighting for each address of each interface with a hardware address, or one with none
    for an interface that has no address. It is dated by when the manager last heard from the
    agent, since that is the last time the machine is known to have been there."""
    cards, addresses = _cards(interfaces), _addresses(networks)
    seen: list[NewSighting | None] = []
    for machine in found:
        listed = known.get(machine.agent_id)
        at = listed.last_seen if listed is not None else now
        name = machine.hostname or machine.name
        for card, macs in cards.get(machine.agent_id, {}).items():
            own = addresses.get(machine.agent_id, {}).get(card) or (None,)
            seen.extend(
                NewSighting.of(
                    mac, at, address=None if address is None else str(address), hostname=name
                )
                for mac in macs
                for address in own
            )
    # An interface was kept for a hardware address that is a device's, so none is left out here.
    return [sighting for sighting in seen if sighting is not None]
