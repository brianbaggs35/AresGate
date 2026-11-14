# Integrations

An integration is a system AresGate watches your network through. AresGate only ever reads from
them: it never changes their settings. Open **Integrations** in the menu to see one card for each,
with what it provides, whether it is connected and when AresGate last reached it. Click a card to
connect it, change its settings, test it or disconnect it.

| Integration | What it gives AresGate | How it connects |
| ----------- | ---------------------- | --------------- |
| OPNsense | Health, interfaces and traffic, gateways, the firewall log, ARP and DHCP, and the services that run on it: Suricata, CrowdSec, OpenVPN, WireGuard, IPsec, Unbound, Dnsmasq, Kea, the ntopng and Wazuh agent plugins, and Zenarmor | API key and secret |
| ntopng | Traffic of each host and of the interface, the devices it sees, and its alerts | Authentication token, or user name and password |
| Wazuh | Alerts, vulnerabilities and each machine's ports and software from the indexer, and the health of the agents from the manager | Two connections, each with a user name and password |
| CrowdSec | The ban decisions CrowdSec has made | A bouncer's API key |
| VirusTotal | How many security vendors flag each internet address an incident names, and who owns it | An API key, and whether it is a free or a premium key |
| AlienVault OTX | Which threat reports from the OTX community name each internet address an incident names, and what they say it is part of                                                                                                         | An API key, and how fast to look things up            |
| GreyNoise | Whether each internet address an incident names is one of the many that scan every address, or belongs to a common business service | An API key and the plan it belongs to, or no account at all |
| NIST NVD | What the National Vulnerability Database says of each CVE an incident names: how severe it is, whether CISA has seen it exploited, and what it is | An API key, or none at all |
| Fingerbank | What each device on the network is, from its hardware address: its make and model, its operating system and how sure Fingerbank is | An API key, and whether the devices in incidents and threats are identified too |

Each card's page starts with the steps to get what it asks for, taken from the product's own
documentation, and a link to that documentation. The steps below are the same ones.

## OPNsense, and everything that runs on it

Suricata, CrowdSec, OpenVPN, WireGuard, Zenarmor and the rest are plugins of OPNsense, and
OPNsense's API reaches all of them with the one key. So they are not separate integrations:
connect OPNsense once, and testing the connection finds which are installed and running. They are
listed under **Services** on the OPNsense page, each with its state (running, stopped, not
installed, or not allowed for the key's user), and each can be switched off if you don't want it
read. The card on the list shows the ones in use.

The first time the connection works, the services it finds **installed but not running** (say, a
Suricata or CrowdSec you stopped) are switched off for you, and the test says which, so AresGate
doesn't try to read what isn't there. It is only a starting point: switch one back on whenever
you like, and later tests leave your choice alone. A service that isn't installed needs no switch,
because it is skipped, and is read as soon as a test finds it installed.

1. In OPNsense, open **System, Access, Users** and make a user for AresGate, or edit one.
2. Give that user only the privileges to view what AresGate collects: diagnostics, interfaces,
   gateways, the firewall log, intrusion detection and the services you run. OPNsense applies the
   same permissions to the API as to its web pages, and a key can do whatever its user can, so a
   user who can only view means AresGate can only view.
3. Under **API keys** on the user, click **+**. OPNsense downloads `apikey.txt` with the key and
   the secret. The secret is shown once, so make a new key if it is lost.
4. In AresGate, enter the address you open OPNsense at, and paste the key and the secret.

### The firewall log

Once OPNsense is connected, AresGate reads the firewall's log every 30 seconds and keeps each
line as an event ([Stored events](operations.md#stored-events)): when it happened, the interface,
what the firewall did with the traffic (`pass`, `block` and so on), which way it was going, the
protocol, the addresses and ports, and the description of the rule that logged it. A block is
recorded as low severity and anything else as info. The line as OPNsense gave it is kept too.

- **What it reads.** The newest 1000 lines of `/api/diagnostics/firewall/log` each time, which
  is more than a home firewall logs in 30 seconds. Lines the next read finds again are stored
  once. Only the traffic your rules are set to log is in the log: in OPNsense, open
  **Firewall, Rules** and turn on **Log** for the rules you want to see.
- **What the user needs.** Two privileges in OPNsense: **Diagnostics: Logs: Firewall: Live
  View**, which covers the log, and **Lobby: Dashboard**, which covers the system time and
  is the one the connection check already needs. Without the first, the job shows the problem on
  the Collection card.
- **The time.** OPNsense's log gives each line's time in the firewall's own time zone, and the
  older log format doesn't even say the year. So each time it reads, AresGate asks the firewall
  for the time on its clock and takes the difference from its own, to the nearest quarter of an
  hour, as the time zone. If the two clocks are more than five minutes apart after that, the
  times in the log can't be trusted, so it stores nothing and says by how much on the Collection
  card. Set the right time on whichever is wrong (**System, Settings, General** on OPNsense).
- **Switching it off.** Switch off **Firewall and system** under Services on the OPNsense page.
  The events that were stored are kept for their retention period.

### Suricata alerts

If Suricata (OPNsense's intrusion detection) is installed, AresGate reads its alerts every
minute and keeps each as an event ([Stored events](operations.md#stored-events)): the signature
that matched, the interface, the protocol, the addresses and ports, and what Suricata did about
it. An alert it let through is recorded as medium severity and one it blocked (in intrusion
prevention mode) as low. OPNsense's query leaves out Suricata's own severity and category, so
that is all AresGate can go by.

- **What it reads.** The newest 500 alerts of `/api/ids/service/query_alerts` each time, which
  is a search that changes nothing. Alerts the next read finds again are stored once. The record
  is kept as OPNsense gave it, except for the packet that set the alert off and the stream
  around it (`packet`, `stream` and the like), which stay on the firewall. Only the start of the
  packet's data is kept (the first 128 bytes and 400 characters), unless it looks like it carries a
  password, a token or a key, so an incident can show what was sent; set
  `ARESGATE_KEEP_PACKETS=false` to keep none of it. The certificate, request, lookup and ssh
  banners Suricata read are shown on the incident too (see
  [What was said on the wire](threats.md#how-it-travelled-and-what-it-was)).
- **What the user needs.** **Services: Intrusion Detection** in OPNsense. It covers all of
  `/api/ids/`, so unlike most of what AresGate reads it also allows changing the rules; AresGate
  only searches the alerts, but make the user for AresGate with only the privileges it needs.
- **When it runs.** Only if testing the connection found Suricata installed, so a firewall
  without it has no such job, and AresGate starts one within a few minutes of the plugin being
  installed. Switch off **Suricata** under Services on the OPNsense page to leave it alone. The
  alerts that were stored are kept for their retention period.
- **Nothing in the list.** An alert log that doesn't exist yet is an empty list, so a quiet
  network and a Suricata that has never alerted look the same. If OPNsense can't ask Suricata at
  all (it answers with nothing), the Collection card says so.

### CrowdSec on OPNsense

If the CrowdSec plugin (`os-crowdsec`) is installed, AresGate reads its bans and its alerts every
minute through the same OPNsense connection, with no second key, and keeps each as an event
([Stored events](operations.md#stored-events)). A CrowdSec that runs anywhere else is the separate
[CrowdSec](#crowdsec) integration; if the same ban is read both ways it is stored once, because
both give it the same identity.

- **Bans.** The decisions in force, as `decision` events with the address, the scenario that
  fired, for how long it runs and where the address is (the country and the network's name, when
  the plugin knows them). As with the other CrowdSec integration, only the origins about your
  network are kept (`crowdsec`, `cscli`, `cscli-import` and `console`, never the community
  blocklist), a ban is medium and any other remedy is low, and an event is dated by the run that
  first saw it. A ban that has run out is left out. How many are in force is the metric
  `decisions.active`, labelled with the connection `opnsense`, so a run that finds none still
  records that there are none.
- **Alerts.** What the scenarios noticed, as `alert` events with the scenario, the address, where
  it is and what was decided (`ban:1`). Unlike a ban, an alert says when it was made, so it is
  dated by that. It is medium when CrowdSec decided something about it and low when it only
  noticed. A row whose time has no time zone is left out, because nothing says which it is in.
- **What it reads.** `/api/crowdsec/decisions/search` and `/api/crowdsec/alerts/search`, the
  searches behind the tables of the plugin's own pages, for the newest 1000 rows each time. They
  run `cscli decisions list` and `cscli alerts list` on the firewall and change nothing.
- **What the user needs.** **CrowdSec** in OPNsense's privileges. It covers all of
  `/api/crowdsec/`, so unlike most of what AresGate reads it also allows lifting a ban or
  changing the plugin's settings; AresGate only searches, but make the user for AresGate with only
  the privileges it needs. Without it, the plugin is listed under Services as not allowed for the
  key's user, and the Collection card shows both jobs failing with *OPNsense didn't accept the
  credentials, or the user isn't allowed to read this (HTTP 403)*.
- **When it runs.** Only if testing the connection found the plugin installed, and AresGate starts
  within a few minutes of the plugin being installed. Switch off **CrowdSec** under Services on
  the OPNsense page to leave it alone. What was stored is kept for its retention period.
- **Nothing in the list.** When `cscli` prints nothing the plugin answers *unable to retrieve
  data*, and `cscli` prints nothing both when no one is banned and when CrowdSec is not running.
  AresGate reads it as none, so a CrowdSec that has stopped looks like a quiet network; the
  Services list, which asks the plugin for its status, shows it as stopped.

#### Where this comes from, and what isn't tried

Taken from OPNsense's and the plugin's own pages and source, not guessed:

- The calls are in OPNsense's
  [API reference for the plugin](https://docs.opnsense.org/development/api/plugins/crowdsec.html),
  which lists the controllers but not what a row holds.
- The rows, from the plugin's source in the
  [opnsense/plugins](https://github.com/opnsense/plugins/tree/master/security/crowdsec)
  repository: `AlertsController.php` and `DecisionsController.php` (an alert's `id`, `value`,
  `reason`, `country`, `as`, `decisions` and `created`; a decision's `id`, `source`, `scope_value`,
  `reason`, `action`, `country`, `as`, `events_count`, `expiration` and `alert_id`, with the ones
  that ran out left out and *unable to retrieve data* for nothing),
  `actions_crowdsec.conf` (the `cscli` commands behind them) and `ACL.xml` (the privilege).
- That a search takes its row count from the body of a POST, in core's search form.

Not tried against a live firewall: the answers are tested against a stand-in built from those
pages. That the time of an alert is written the way `cscli` writes its dates (RFC 3339), and that
the decisions list leaves out the community blocklist as `cscli` does when run by hand, are
assumed; an alert whose time can't be read is left out, the origins kept make the second not
matter, and the Collection card and the API log show what the firewall answered.

### Health, traffic and gateways

Once OPNsense is connected, AresGate reads how the firewall is doing every minute and keeps the
numbers as metrics ([Stored metrics](operations.md#stored-metrics)), so they can be charted over
time. There are four jobs, so that a missing privilege costs only the numbers it covers; each
shows on the Collection card with its own state.

| Job | Keeps | Reads | The user needs |
| --- | --- | --- | --- |
| System health | The load averages (`system.load_1m`, `_5m`, `_15m`), `system.uptime_seconds`, the memory in use and in all, and, for each disk, `disk.used_percent`, `disk.used_bytes` and `disk.total_bytes` | `system_time`, `system_resources` and `system_disk` under `/api/diagnostics/system/` | **Lobby: Dashboard**, the privilege the connection check already needs |
| Processor use | `cpu.usage_percent` | `/api/diagnostics/activity/get_activity` | **Diagnostics: System Activity** |
| Interface traffic | For each interface, the bytes, packets and errors in and out, and the packets dropped (`interface.bytes_in` and so on) | `/api/diagnostics/interface/get_interface_statistics` | **Diagnostics: Netstat** |
| Gateways | For each gateway, `gateway.up` (1 or 0), `gateway.latency_ms`, `gateway.jitter_ms` and `gateway.loss_percent` | `/api/routes/gateway/status` | **System: Gateways** |

- **Counters.** The traffic of an interface is kept as OPNsense counts it: a number that only
  rises, from zero when the interface came up. A chart finds the speed from the difference
  between two readings.
- **Which interfaces and disks.** Each interface is named as OPNsense names it (`igc0`). The
  firewall's own loopback and its logging, state-sync and encapsulation interfaces are left
  out. Of the file systems, only those on a disk (UFS and ZFS) are kept, by mount point; an
  older OPNsense gives the percentage in use but not the bytes.
- **Gateways.** A gateway is up unless OPNsense's monitoring says it is down, or forced down. One
  with a poor link is still up, and its delay and loss show how poor. A gateway whose monitoring
  is switched off has no delay or loss to keep, and is always up, because OPNsense has nothing
  to say against it.
- **Processor use.** OPNsense has no way to ask for a single reading except its system activity
  page, which runs `top`; that takes it a couple of seconds, once a minute.
- **When it reads.** At the moment each run begins, by AresGate's clock, so the firewall's own
  clock doesn't matter. Switching off **Firewall and system** under Services on the OPNsense
  page stops all four jobs, and the firewall log. The metrics that were stored are kept for their
  retention period.

### Devices

AresGate keeps a list of the devices it has seen on the network, so that a page or the AI
analyst can say which device an address belongs to ([Stored devices](operations.md#stored-devices)).
A device is told apart by its hardware (MAC) address, and has the addresses it has had, a host
name if it gave one, who made its network card, and when it was first and last seen. Three jobs
of OPNsense fill the list; each shows on the Collection card with its own state. A fourth, the
hosts ntopng lists, adds the ones it knows the MAC address of
([below](#hosts-and-the-devices-among-them)).

| Job | Reads | Every | The user needs |
| --- | --- | --- | --- |
| Devices (ARP table) | `/api/diagnostics/interface/get_arp` | minute | **Diagnostics: ARP Table** |
| Devices (Dnsmasq leases) | `/api/dnsmasq/leases/search`, for IPv4 and IPv6 | 5 minutes | **Services: Dnsmasq DNS/DHCP: Settings** |
| Devices (Kea leases) | `/api/kea/leases4/search`, for IPv4 | 5 minutes | **Services: DHCP: Kea(v4)** |

- **Which jobs run.** The ARP table is part of **Firewall and system**. The lease jobs run only
  if testing the connection found Dnsmasq or Kea installed, so a firewall with neither has only
  the ARP table, and AresGate starts one within a few minutes of the plugin being installed.
  Switch off
  **Dnsmasq** or **Kea DHCP** under Services on the OPNsense page to leave it alone.
- **The ARP table** is what the firewall has learned about the devices on its networks, and
  includes its own addresses. An entry that has gone stale (the device stopped answering) is not
  a sighting. It gives the hardware and IP address and who made the network card; it has no host
  name unless the firewall knows one.
- **Leases** give the host name the device asked for, and the address it was given. Dnsmasq
  lists the leases it has given out that haven't run out; of Kea's, only those in force count,
  not a lease that was declined or has run out and waits to be cleared away. A client that gave no hardware address
  (an IPv6 client of Dnsmasq that identifies itself some other way) can't be told from the
  others, so it is left out. Kea's IPv6 leases are a privilege of their own and aren't read yet.
- **What the user needs.** The two DHCP privileges cover all of `/api/dnsmasq/` and, for Kea,
  all of `/api/kea/dhcpv4/`, `/api/kea/leases4/` and `/api/kea/service/`, so unlike most of what
  AresGate reads they also allow changing the settings and releasing leases. AresGate only searches the leases; make the
  user for AresGate with only the privileges it needs, and leave out the ones for a server you
  don't run.
- **Last seen.** It is when a job last listed the device. A lease is listed until it runs out,
  so a device that has left but holds a long lease keeps being seen; the ARP table is the
  better sign that it is there now.
- **Randomized addresses.** A phone or laptop that uses a different hardware address for each
  network, or changes it from time to time to keep from being followed, appears as a new device
  each time it does.
- **The Assets page.** It shows these devices with the ones ntopng lists and Wazuh's agents,
  each with the programs that listed it: the ARP table makes a device "online" (a device is only
  online when something that can only list what is on the network now has listed it in the last
  ten minutes), while a lease only makes it "seen recently", since a lease outlasts the device.

**Zenarmor** has an API of its own, on a port of its own, that takes a key made in Zenconsole
(register the firewall there, enable the API and make a key). It has its own switch on the
OPNsense page, **Use Zenarmor API**, with its own address, user and key, and its own certificate
settings. Leave it off if you don't use Zenarmor. **It needs a paid Zenarmor subscription:**
Zenarmor's documentation lists API access (and custom reports and exports) among the features of
its paid editions, not the free one, so with the free edition the connection may be refused. You
lose nothing by leaving it off, because everything else about the firewall comes through OPNsense's
own API.

**Suricata** has no API outside OPNsense: it is the intrusion detection plugin, and it appears
under Services; its alerts are read as above. **CrowdSec** on OPNsense is read the same way (see
[CrowdSec on OPNsense](#crowdsec-on-opnsense)). A CrowdSec that runs anywhere else (a Raspberry
Pi, a server) is the separate **CrowdSec** integration below.

## ntopng

1. In ntopng, edit the user AresGate will use and generate its **User Authentication Token**.
2. Choose **Authentication token** and paste it, or choose **Username and password** to use HTTP
   basic authentication instead.
3. Press **Fetch interfaces** and choose the **Interfaces** AresGate reads, one or several. The list is asked of
   ntopng with the address and sign-in as they are filled in, before anything is saved, and a
   connection that is saved asks as the page opens. Each interface is named as ntopng names it
   (`LAN (eth1)` when ntopng shows a name other than the system's), with its ID, what it takes its
   traffic from (a live capture, flows from an exporter, a capture file) and what it has seen
   since ntopng started: its hosts, flows and bytes, or "no traffic seen yet". ntopng's list
   gives no speed or address for an interface, so none is shown.

Up to 16 can be chosen, and they are kept as their IDs joined by commas, lowest first (`0,1`);
a connection saved with one ID before several could be chosen reads as that one. **No number is
assumed**: ntopng gives its interfaces IDs itself, with gaps and not always from 0 (an OPNsense
firewall's might be 1, 2, 3 and 6), so choosing none is allowed, and then every interface ntopng
lists is read except the loopback (`lo`, `lo0`), which only carries the machine's traffic to
itself. Which they are is asked of ntopng each time a collector runs, so a renumbered ntopng
needs no change here, and the test says which it reads. If only a loopback is listed, it is
read. Every collector below reads each chosen interface in turn: the interface's traffic is kept
for each, labelled with the interface's name; hosts and alerts from all of them are read
together, and an alert says which interface it came in on, so it can later be placed on a part
of the network ([Interfaces](development.md#interfaces-the-parts-of-the-network)). An interface
that has seen nothing is skipped by the *Interface traffic* collector, unless every chosen
interface is quiet.

A connection that isn't saved yet starts on every interface that has seen traffic (or the first,
if none has), leaving out the loopback, when Fetch interfaces is pressed. A saved choice that has
gone from the list is kept and flagged, never swapped silently: the test says "ntopng answered,
but has no interface with ID 0. It has: ID 1: WAN (igc0), ID 2: LAN (igc1), ID 3: lo0
(loopback), ID 6: ovpns1" and suggests the IDs to choose (all but the loopback), and the field
under Interfaces offers a button that chooses them in one click. The list is asked again after
every test, so the button is there without pressing Fetch interfaces. A loopback can still be
chosen, and the test then says it normally has nothing worth reading. ntopng answers an `ifid`
it doesn't have with HTTP 400 (`INVALID_INTERFACE`), which the collectors report as "ntopng has
no interface 3, so it refused the request. It has: ID 0: eth0, ID 1: LAN (eth1)" instead of the
bare status. An interface that has seen nothing is reported in words by the test and by the
*Interface traffic* collector, so "nothing comes in" has a reason on the page. Asking for the
list makes one request for the list and one for each of the first 20 interfaces, and each is in
the API log.

ntopng answers a login it refuses by redirecting to its login page. AresGate doesn't follow
redirects (see below), so a refused token shows up as "redirected to its login page".

The user must be allowed to see alerts, which ntopng treats as a capability of its own, and
AresGate only reads. Everything below is read from the **Interfaces** chosen above, every minute.

### Hosts and the devices among them

For every host on the local networks ntopng lists (`mode=local`) AresGate keeps five readings as
metrics, labelled with the host's address: `host.bytes_sent` and `host.bytes_received` (what it
has sent and received since ntopng first saw it), `host.throughput_bps`, `host.flows` (the flows
it is in now) and `host.score` (how suspicious ntopng finds its behaviour so far). The byte
counters rise, so a chart takes the difference between two readings; ntopng starts a host's again
when it has forgotten the host, which shows as a drop. Up to 1000 hosts are read.

A host is also a **device** (see [Devices](#devices)) when ntopng says it is in its broadcast
domain and knows its MAC address, with the name ntopng has for it. A host behind a router is
left out of the devices, because the MAC address ntopng has for it is the router's.

### The interface's traffic

How much has come in and gone out (`interface.bytes_in`, `interface.bytes_out`, packets and
drops, and how much went from local hosts to remote ones and back), and how many hosts, local
hosts, devices and flows ntopng holds and how many alerts are engaged, as metrics labelled with
the interface's name. The names are those OPNsense's interface traffic uses, so a chart can show
either. ntopng's own `throughput_bps` isn't read: its documentation doesn't give the unit, and
the speed is the difference between the counters.

### Flow alerts and host alerts

Every minute the alerts of the last half hour (the newest 500 of each kind) become events
(`alert`), dated by when the alert began: what ntopng found, how serious it rates it, and the
hosts and ports it is about. An alert is stored once, by what it says and when it began, so one
that is still engaged is the same event on every run.

- **How serious.** ntopng's severity (none, debug and info are info, a notice is low, a warning
  medium, an error high, critical and emergency critical). The grouping is AresGate's.
- **Addresses.** A flow alert's source is the client and its destination the server, with their
  ports and the protocol. A host alert is about one host: it is the source if ntopng calls it the
  attacker, and otherwise the destination, so it can be matched with the firewall's and Wazuh's
  events about that host.
- **Not read.** ntopng also keeps alerts for the interface, for networks, devices (MAC
  addresses), its own system and monitored hosts. AresGate doesn't read those yet.

### Packets of a host

On a device's page (**Assets**, then the device) the **Packets** card has ntopng listen to one of
the device's current addresses for 5, 10, 20 or 30 seconds and shows what it saw, as ntopng's
live capture (`GET /lua/rest/v2/get/pcap/live_traffic.lua`, which takes `ifid`, `host` and
`duration`) sends it: a classic pcap file. For each packet there is how long after the first it
came, who sent it to whom with the ports, the protocol (and the flags of a TCP segment, or whether
an ARP message asks or answers), its size on the wire and the first 48 bytes it carried, with what
isn't printable shown as dots. It is for looking at what a device is doing, a camera that talks
when it should be asleep, say. What to know:

- **Nothing is kept.** The file is read, shown and thrown away, and it never goes to an AI
  provider. Encrypted traffic shows as it is: bytes that mean nothing.
- **It is limited.** At most 2 MB of the answer is read (the card says when the end is missing),
  the first 300 packets are listed (all are counted), and one capture runs at a time, since ntopng
  holds the interface for each. Frames that are neither IP nor ARP are counted and not shown.
- **It is on one interface.** The first one the connection reads (the lowest **Interface** ID
  chosen, or the first ntopng lists that isn't the loopback when none is chosen). A device that
  is on another one of a firewall's interfaces is seen with no packets.
- **It is on record.** Each capture is in the audit log (**Settings**, then **Activity**) with the
  host, the seconds and how many packets it held, and in the API log with its path and no query.
- **The user needs the permission.** ntopng only sends a capture to a user allowed to download
  PCAP files, which an administrator is and a non-privileged user isn't unless it was given it.
  Without it the card says what ntopng said. Reading packets is more than the alerts and
  measurements AresGate otherwise asks for, so use a separate user for it if you want.

The capture is `POST /api/captures` with `host` and `seconds`. It answers 409 when ntopng isn't
connected or another capture is running, 422 for something that isn't an IP address, and 502 with
ntopng's reason when it couldn't give one. Read from ntopng's source
(`scripts/lua/rest/v2/get/pcap/live_traffic.lua`) and its REST API specification, and not tried
against a live ntopng, which the stand-in in the tests answers like.

### Where the ntopng reading comes from

ntopng's documentation has the endpoints and an example of each answer, but not the parameters
they take, so those are read from ntopng's source. Taken from them, not guessed:

- The [REST API v2 examples](https://www.ntop.org/guides/ntopng/api/rest/examples_v2.html) show
  `get/host/active.lua` (2.2.1), `get/interface/data.lua` (2.1.1), `get/ntopng/interfaces.lua`
  (2.1.4) and the alerts list (2.4.2), with the `rc` and `rsp` of every answer.
- The parameters (`mode`, `all`, `status`, `epoch_begin`, `epoch_end`, `length`, `sort`, `order`)
  and the fields of an alert record are in ntopng's source, in
  [`get/host/active.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/get/host/active.lua),
  [`get/interface/data.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/get/interface/data.lua),
  [`get/flow/alert/list.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/get/flow/alert/list.lua),
  [`get/host/alert/list.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/get/host/alert/list.lua)
  and the [alert store](https://github.com/ntop/ntopng/tree/dev/scripts/lua/modules/alert_store).
  That source is the development branch.

Not tried against a live ntopng: the answers are tested against a stand-in built from those
pages, and a ntopng of another version may differ. If it does, the Collection card says so and the
API log shows the answer. What was worked out rather than read: that the `status` value `any`
includes the alerts that are engaged, and which of ntopng's severity numbers is which (from its
list of severities).

### What ntopng has that AresGate doesn't read yet

ntopng also knows the application protocols and categories of every host's traffic, the flows
themselves, historical traffic charts, and a host's alerts by type. AresGate doesn't read those
yet.

## Wazuh

Wazuh has two connections, each with its own address and sign-in:

- **Manager API** (port 55000): create an API user for AresGate in the dashboard (Server
  management, Security, Users) and link the `agents_readonly` role to it, rather than using the
  administrator.
- **Indexer** (port 9200): create an internal user, and a role with the index permission `read`
  on `wazuh-alerts-*` and `wazuh-states-*` and no cluster permission, mapped to that user, rather
  than using `admin`. The indexer's users are separate from the manager API's. The second pattern
  is for the vulnerabilities and the inventory: a user that may read only the alerts still gets
  them, and the two collectors that read the others say what to allow.

Both use HTTPS with a certificate Wazuh made in a default install, so see
[Certificates are verified](#what-aresgate-will-connect-to) below. A Let's Encrypt certificate on
the **dashboard** (the only part Wazuh's own page on third-party certificates covers) isn't the
one these two answer with:

- **Manager API**: its certificate is self-signed by default (`server.crt` in
  `/var/ossec/api/configuration/ssl`, set in `api.yaml`). Choose **Only this exact certificate**,
  click **Look up the certificate**, and compare the fingerprint with the one on the Wazuh server
  (`openssl x509 -in /var/ossec/api/configuration/ssl/server.crt -noout -fingerprint -sha256`).
- **Indexer**: its certificate comes from Wazuh's certificate tool, which also makes the authority
  that signed it, `root-ca.pem`. Choose **A certificate authority I paste** and paste `root-ca.pem`
  (never `root-ca.key`), or pin the certificate. The tool puts the addresses it was given in the
  certificate, so use one of them in the address.
- To have **The certificates this computer trusts** work, install a public certificate on the API
  and the indexer too; that isn't covered by Wazuh's Let's Encrypt page.

### Alerts

Every minute AresGate searches the indexer's `wazuh-alerts-*` indices for the alerts of the last
half hour (the newest 500) and keeps each as an event (`alert`): when it was raised, the rule and
the level Wazuh rates it at, the host (agent) it is about, the source address and port Wazuh's
decoders found in the log line, and Wazuh's own record of it, including the log line itself. An
alert is stored once however often it is read, by its document's id in the index.

- **How serious.** Wazuh's levels run from 0 to 16. Up to 3 is routine (ignored, a notification,
  a login that worked) and shows as info, 4 to 6 as low (errors, a low relevance attack), 7 to 10
  as medium (a first time seen, an error from an invalid source, repeated user errors), 11 to 13
  as high (an integrity warning, the events Wazuh calls high importance) and 14 and up as critical
  (its high importance security events and severe attacks). Wazuh's table names the levels; where
  AresGate draws the lines between them is its own choice.
- **Addresses.** An alert's source is the address in its log line (`srcip`), such as the one an
  SSH login failed from. Its destination is the one the line names (`dstip`), or else the host
  that raised it, so an alert can be matched with the firewall's and Suricata's events about that
  host.
- **What the user needs.** For the alerts, read access to the `wazuh-alerts-*` indices and nothing
  else: the index permission `read`, and no cluster permission (the vulnerabilities and the
  inventory below also read `wazuh-states-*`). The manager's API doesn't give alerts, so
  this is the only place AresGate reads them. The connection test makes the same search as the
  collector (asking for no alerts), so a test that passes means the collector is allowed what it
  does. It doesn't ask the indexer's root page for the version, which needs the cluster
  permission `cluster:monitor/main` and would refuse a user that can read every alert.
- **When the test says no.** A wrong user name or password is HTTP 401: the indexer's own users
  are under Indexer management, Security, Internal users. A user that signed in but isn't allowed
  is HTTP 403, and the indexer's reply names the permission, such as
  `indices:data/read/search`; the test passes on that name and nothing else the indexer said.
  The usual causes are a user that isn't mapped to its role (Mapped users) and an index pattern
  that doesn't match `wazuh-alerts-*`.
- **A gap.** An alert that reaches the indexer more than half an hour after it was raised, such
  as after the indexer was down, is not read. A manager that raises more than 500 alerts in half
  an hour is read from the newest.

### Agents

Every minute AresGate signs in to the manager's API for a token and lists the agents. How many
are in each state (`active`, `disconnected`, `pending`, `never_connected`) is kept as the metric
`agents.count`, with a zero for a state that has none. An agent that is disconnected is also an
info event (`agent`, "laptop (192.168.1.41) stopped reporting to Wazuh"), dated by when the
manager last heard from it, since a host that stops reporting is the first thing an intruder with
the run of it may do. It is stored once; an agent that reports again and goes quiet again is a
new event. The manager itself, which the API lists as agent `000`, is not counted. The user needs
a role that may read agents, such as `agents_readonly`. A user without one signs in without
trouble, and the API answers 200 with an empty list instead of refusing, so the manager's own
agent `000` missing from the list is how the connection test and the Agents collector tell, and
say so, rather than counting zero agents every minute.

Each agent is also listed on the [Assets page](ui.md#assets) as a machine, by the name and IP
address Wazuh has for it (the manager gives no hardware address): an active agent was heard from
now, another when it last reported in, and one that never has (`pending`, `never_connected`) is
not listed. The page matches it to the device that had its address, or else to the one device
that has the same short host name, and says so on the card; an agent that matches no device is an
asset of its own. If the manager lists every agent, the ones it no longer lists are removed.

### Where this comes from, and what isn't tried

Taken from Wazuh's documentation, not guessed:

- The ports (55000 for the server API, 9200 for the indexer) are in
  [Architecture, Required ports](https://documentation.wazuh.com/current/getting-started/architecture.html).
- The token request and `raw=true` are in the
  [server API's Getting started](https://documentation.wazuh.com/current/user-manual/api/getting-started.html).
  `GET /agents`, its `limit`, `select` and `status` parameters and the agent's `lastKeepAlive` are
  in the API's [OpenAPI specification](https://github.com/wazuh/wazuh/blob/v4.14.1/api/api/spec/spec.yaml).
- The search is the
  [indexer API's](https://documentation.wazuh.com/current/user-manual/indexer-api/getting-started.html)
  (OpenSearch) `_search`, and the alert fields are those of the
  [`wazuh-alerts-*` index template](https://github.com/wazuh/wazuh/blob/v4.14.1/extensions/elasticsearch/7.x/wazuh-template.json).
- The levels are in
  [Rules classification](https://documentation.wazuh.com/current/user-manual/ruleset/rules/rules-classification.html).
- What the indexer's user may do is OpenSearch's security plugin: the permission
  `cluster:monitor/main` is listed under
  [Permissions](https://docs.opensearch.org/latest/security/access-control/permissions/), the
  action groups `read` and `cluster_monitor` under
  [Default action groups](https://docs.opensearch.org/latest/security/access-control/default-action-groups/),
  and the name `cluster:monitor/main` is the `NAME` of `MainAction` in OpenSearch's source. The
  pages don't say that the root page (`GET /`) is the request that needs it; that was tried.

Tried against a real OpenSearch 2.19.1 with its security plugin, which the Wazuh indexer is built
on, and a real Wazuh 4.14.1 manager, both in Docker (not against Wazuh's own indexer build, or
other versions): a user with the index permission `read` on `wazuh-alerts-*` and no cluster
permission can make AresGate's search, including when no alert index exists yet, and gets 403 for
`GET /`, with the same result for Wazuh's own read-only example role (`cluster_composite_ops_ro`
and `read` on every index). A wrong password is 401, and a user with no role is 403 naming
`indices:data/read/search`. On the manager, a user with no role gets 200 and an empty list from
`GET /agents`, and one with `agents_readonly` linked to it (through `POST
/security/users/{user_id}/roles`) also gets agent `000`. Everything else is tested against a
stand-in built from the pages above. If your version answers differently, the Collection card says
so and the API log shows the answer.
What was worked out rather than read: that `data.srcip`, `data.dstip` and `data.srcport` are
where the decoders put an address (they vary by decoder, so an alert without them is kept without
an address), and that an agent's `lastKeepAlive` always carries a zone, as the specification's
examples do (one that doesn't is left out).

### Vulnerabilities

Every 15 minutes AresGate searches `wazuh-states-vulnerabilities-*` for the flaws the manager's
vulnerability scanner found in the software its agents report. Each is an event of the kind
`vulnerability`: the CVE as its signature, the package and version, the machine (the agent's name,
and its address when the manager has listed the agent), and how serious Wazuh rates it, from its
`Low`, `Medium`, `High` and `Critical` (anything else is info). The summary reads "CVE-2024-13176
in openssl 3.0.13 on web1 (High, CVSS 7.5)".

- **Once, when first seen.** A flaw is dated by the run that first saw it, not by when Wazuh
  detected it: a flaw found a month ago isn't news of today, and a date that old would be outside
  what is kept. It is told by the agent, the CVE and the package with its version, so reading it
  again changes nothing, a package that is updated and still affected is a new event, and the same
  flaw on two machines is two. Wazuh removes a flaw it no longer finds; the event stays until it
  is old enough to be deleted, and is then stored again if the flaw is still there.
- **Not an incident.** A flaw is not an attack, so these events are never part of an incident and
  are not on the Dashboard's list of alerts. They are in the [event search](ui.md) (kind
  `vulnerability`), and the analyst can be asked about them.
- **A limit.** A run keeps the 1,000 with the highest CVSS score, which a home network doesn't
  reach.

### Inventory

Every 15 minutes AresGate reads what each agent's inventory module reports, from the indexer's
`wazuh-states-inventory-system*`, `-interfaces*`, `-networks*`, `-packages*` and `-ports*`:

- **The machines.** Each agent's host name, operating system and version, architecture and
  kernel, the hardware addresses of its network cards and their IP addresses, the ports that
  listen (TCP and UDP, the address, the port and the program), and every package installed, kept
  for the analyst to be asked about: "what does web1 listen on?", "which machines have openssl,
  and which version?". What an agent says now replaces what it said, and a machine the indexer no
  longer lists is forgotten with its ports and software.
- **The devices.** A network card of a machine becomes a device, told apart by its hardware
  address like every other, with each IP address the card has and the machine's name, so the
  firewall's ARP table and the agent's inventory are one device, not two. It is listed as
  **Agent inventory**, which never counts as on the network now: an agent that stopped reporting
  an hour ago still has the same cards. A card is left out when it is down, has no hardware
  address, or is a bridge or virtual cable (`lo`, `docker*`, `br-*`, `veth*`, `virbr*`, `cni*`,
  `flannel*`, `cali*`, `tun*`, `tap*`, `vmnet*`, `vboxnet*`), and so is a loopback or link-local
  address. The device is dated by when the manager last heard from the agent.
- **A limit.** A search asks for at most 10,000 documents of each index, so a machine with more
  than that isn't read in full. When the system index holds more than was read, nothing is
  forgotten.
- **The permission.** Read on `wazuh-states-*`. A user without it is refused (HTTP 403) and the
  Collection card says to add it; the connection test, which only searches the alerts, doesn't
  check it.

### Where the states come from, and what is inferred

The manager's API had endpoints for the inventory (`GET /syscollector/{agent_id}/…`). Wazuh issue
[31299](https://github.com/wazuh/wazuh/issues/31299), closed on 1 September 2025 and tracked under
release 5.0.0, removes them, and says the inventory is stored in the indexer; it names no
replacement, and was not checked against a running 5.0. So this reads the indexer, which holds the
same data and is what Wazuh's own dashboard reads, and uses no manager endpoint for it.

The field names are those of the index templates in Wazuh's source at release 4.14.1,
`src/wazuh_modules/vulnerability_scanner/indexer/template/index-template.json` and
`src/wazuh_modules/inventory_harvester/indexer/template/wazuh-states-inventory-*.json`: the
`agent.id` and `agent.name` of each document, `vulnerability.id`, `.severity`, `.score.base`,
`package.name` and `.version`, `host.os.*`, `host.hostname`, `host.architecture`, `host.mac`,
`interface.name`, `interface.state`, `network.ip`, `network.transport`, `source.ip`,
`source.port` and `process.name`. The development branch of Wazuh's indexer plugins (what
becomes 5.0) puts the agent under `wazuh.agent` instead, so both are read. Wazuh's documentation
site was not reachable when this was written, so its page of
[inventory fields](https://documentation.wazuh.com/current/user-manual/capabilities/system-inventory/available-inventory-fields.html)
was read only in the older form of it in its documentation repository (the agent's own tables,
`sys_osinfo`, `sys_ports` and so on); the templates are the source of truth here.

What could only be inferred, because no page lists the values:

- That a port that listens has the state `listening` (`LISTEN` is also asked for). A UDP port has
  no state in an agent's table, so it isn't listed unless Wazuh gives it one.
- That a port's own end is `source.ip` and `source.port`, and the other end `destination.*`.
- That an interface that is down has the state `down`.
- That `vulnerability.severity` is capitalised, as Wazuh's pages write it (it is compared without
  regard to case), and `vulnerability.score.base` is the CVSS base score.
- That `host.mac` may be one hardware address or a list, as ECS allows.
- Which interfaces belong to a bridge or a container, from their names (the list above).

None of it was tried against a live Wazuh. The stand-in answers with documents of the shapes
above, and tests cover every branch, so an answer that differs shows as an empty list or a
failed collector with the reason on the Collection card, and the API log has the request.

Wazuh's own statistics (`wazuh-statistics-*`) are not read.

## CrowdSec

Where CrowdSec runs, run `cscli bouncers add aresgate`. It prints an API key once, and a bouncer's
key can only read decisions. CrowdSec's local API listens on `127.0.0.1:8080` unless
`api.server.listen_uri` in its `config.yaml` says otherwise: make it listen on an address AresGate
can reach.

The local API speaks plain HTTP unless you set up TLS for it. AresGate accepts `http://` there but
warns that anyone on the network path can read the key.

### Bans

Every minute AresGate asks the local API for the decisions in force and keeps each ban as an event
(`decision`), with the address, the scenario that fired (`crowdsecurity/ssh-bf`), for how long it
runs and CrowdSec's own record of it. A ban is medium, any other remedy (a captcha) is low and a
ban that was only simulated is info. How many decisions are in force is kept as the metric
`decisions.active`, so a run that finds none still records that there are none.

- **Only what happened here.** It asks for the origins `crowdsec` (a scenario that fired on your
  own logs), `cscli` (a ban someone typed in), `cscli-import` (bans imported from a file) and
  `console` (see the end of this section). The community blocklist (`CAPI`) and the lists you
  subscribed to (`lists:*`) are tens of thousands of addresses that attacked other people, and are
  left out so they don't bury the ones that attacked you. `remediation_sync` is left out too,
  because nothing in CrowdSec's documentation says it is about your network.
- **When.** The local API gives no time for a decision, so an event is dated by the run that first
  saw it, which is within a minute of when it was made. A ban seen before is not stored again,
  however long it has lasted, and if its time runs out and CrowdSec bans the address again it is
  a new decision with a new number and is stored again.
- **Ranges.** A ban of a whole range (`203.0.113.0/24`) is kept with its summary, but has no
  source address, because an event's address is one address.
- **Alerts aren't read yet.** The alerts behind the decisions, with the events that made them, need
  a machine login (`cscli machines add`) rather than a bouncer's key, so they come later. The
  CrowdSec plugin on OPNsense gives them already: see
  [CrowdSec on OPNsense](#crowdsec-on-opnsense).

#### Where this comes from, and what isn't tried

Taken from CrowdSec's documentation and source, not guessed:

- What `/v1/decisions` answers is in the
  [local API's bouncer guide](https://docs.crowdsec.net/docs/next/local_api/bouncers).
- That a bouncer's key is for the decisions calls and that alerts need a machine login, and the
  `origins` parameter of `/v1/decisions` and `/v1/decisions/stream`, are in the local API's
  [OpenAPI specification](https://github.com/crowdsecurity/crowdsec/blob/master/pkg/models/localapi_swagger.yaml).
- The origins are listed in CrowdSec's
  [source](https://github.com/crowdsecurity/crowdsec/blob/master/pkg/types/constants.go) and
  described for `crowdsec`, `cscli`, `CAPI` and `cscli-import` in the
  [decisions management guide](https://docs.crowdsec.net/u/user_guides/decisions_mgmt).

Not tried against a live CrowdSec: the answers are tested against a stand-in built from those
pages. If your version answers differently, the Collection card says so and the API log shows the
answer. The `console` origin is in CrowdSec's source, but its documentation doesn't say what the
Console puts under it, so including it is a guess that decisions made in the Console are yours.

#### What CrowdSec has that AresGate doesn't read yet

CrowdSec keeps more than the decisions: its alerts say which events made a decision, with the
country and network (AS) the attacker came from, and a decision lifted early shows in the
decisions stream. Both need a machine login (`cscli machines add`) or the stream rather than a
bouncer's key. AresGate doesn't read those yet.

## VirusTotal

VirusTotal is the one integration AresGate reaches on the internet. Its address is fixed at
`https://www.virustotal.com`, and the API key goes to that address and nowhere else. Copy the key
from VirusTotal's API key page, `https://www.virustotal.com/gui/my-apikey`, while signed in, paste
it on the card, choose the access level and test the connection. AresGate asks nothing until a test
has worked.

Its certificate is one that public authorities vouch for, so AresGate checks it against the
certificates this computer trusts, as a browser checks a site's. There is no certificate to look up,
pin or paste for VirusTotal.

### Access levels

The free public API allows 4 lookups a minute and 500 a day. VirusTotal says it must not be used in
commercial products or services, or in business workflows that do not contribute new files. A
premium key's limits depend on its plan, so the card asks which kind of key you have. AresGate keeps
a free key to 4 lookups a minute, 500 a day and 15,000 in any 30 days. The monthly figure is a
margin of its own, because VirusTotal's pages give none. A premium key is asked about once a second.

VirusTotal keeps a count of its own. When a free key's 500 a day are used up, it refuses every
request until the count resets at 00:00 UTC, and AresGate sends nothing until then. The connection
stays connected. The integration page and the Threat intelligence page say when searches and tests
resume, and the pause is read back from the lookups kept, so a restart doesn't send requests early.
VirusTotal's other refusal, too many requests in a minute, holds requests for a minute.

Every request counts, so AresGate doesn't test the connection on a timer. A test is one lookup of a
public address that always has a report, and it runs only when you press Test. A test that comes
while a limit holds is not sent, and the connection is left as it was.

### What is asked about

Each lookup is about one internet address that an incident from the last seven days names. A
private address is never sent, nor one in the networks of the home's own internet side, since that
would tell VirusTotal where the home is. Lookups go one at a time. An address with no answer kept
is asked about first, the most recent incident's first. Once each has an answer, the lookups keep
the answers up to date: the address whose answer went out of date longest ago is asked about again.
An address that was asked about in the last hour waits, whatever came of it.

VirusTotal's API documentation says that any indicator queried through the API is scanned and added
to its dataset. So every address sent becomes known to VirusTotal, which is worth knowing before
you connect a key.

### How the allowance is spent

A search and a background lookup count toward the same allowance, and each request counts, whether
it is answered or not. On a free key the background lookups are four minutes apart, so they use at
most 360 of the 500 a day and spread them over the whole day, which leaves 140 for searches. A search
is held back only by the 15 seconds between any two lookups and by the day's and the month's
allowances, not by the background's spacing.

### What is kept

Every answer is kept for good, one for each address, domain and web address that was asked about,
and a newer answer takes the older one's place. With it AresGate keeps when the subject was first
asked about, how many answers it has had, and when a newer answer last changed the judgement and
what it was before. This is AresGate's own record of threat intelligence: the AI reads it, and the
Threat intelligence page lists it under "What AresGate knows", newest first. The list can be
searched by part of an address, a name or an owner, and narrowed to one judgement. Reading it
sends VirusTotal nothing and counts toward no limit (`GET /api/threat-intel/subjects`).

VirusTotal has no cheaper way to say whether a report changed than to give the report, so checking
for an update costs a lookup. AresGate spends those where answers change soonest. An answer that
engines flagged, or that had no report yet, is fresh for two days. An answer that no engine flagged
is fresh for a week. A search for a subject whose answer is fresh is answered from what was kept: no
request is sent, nothing is counted, and the report says so and says when the answer is checked
again. Once an answer is no longer fresh, the next search or background lookup of its subject asks
VirusTotal again. A request that got no answer leaves the answer kept as it was.

Check again, in a report, asks VirusTotal for a newer answer at once, fresh or not. It counts toward
the allowance as a search does. A web address is kept without its text, so one opened from the list
has no Check again: search for the address to check it.

A connection test is one lookup too, and it counts toward the allowance. It is sent whenever you
press Test, even if the address it asks about has an answer kept, because it is the key
that is being checked.

A limit on a free key is never a sign that the connection is broken. When VirusTotal answers a test
with its daily quota used up, or asks for fewer requests for a minute, it has been reached and has
taken the key, so the test passes and the connection shows as connected, with the limit noted
beside it. While its daily quota holds, a test sends nothing and the connection stays as it was.
When AresGate's own pacing holds a test (it leaves 15 seconds between lookups on the free level),
the page says so as a notice, with how long to wait, and the connection stays as it was: nothing
was tested, and nothing was found wrong. In the log of requests, one that got HTTP 429 is marked as
held back by a limit, not as failed.

### Correcting what VirusTotal says

One engine can be wrong either way: an address it flags may be a friend's server, and one it has no
complaint about may be the one that has been scanning the network. The owner can say so. A subject
can be ruled **safe** (to correct a false positive) or **suspicious** (to correct a false negative),
with a reason if you like, from the report window, from the "What you have ruled" card on the
Threat intelligence page, or on an address of an incident that is on the internet.

A ruling is the owner's word, so it belongs to no service. It asks VirusTotal nothing, needs no
connection, and can be made about something no service has been asked about. It shows in place of
VirusTotal's judgement on every page: the report window, the list of what AresGate knows (whose
counts and filters follow the rulings), an incident's conversations, and the peers of an asset.
What VirusTotal said stays beside it, with its counts, as what VirusTotal said, and a newer answer
never replaces a ruling. The AI is told of it too, as a fact about the home that stands over the
reputation, and is asked to go by it. Taking a ruling back brings what VirusTotal said back. A
ruling is kept as an address, a domain or the hash of a web address, like an answer, and only
addresses, domains and web addresses on the internet can be ruled on: what is on the home network
is refused.

Rulings are made with `PUT /api/threat-intel/overrides` (`subject`, `verdict` `safe` or
`suspicious`, an optional `note` of up to 500 characters), listed with `GET
/api/threat-intel/overrides` and taken back with `DELETE /api/threat-intel/overrides?subject=`.
Each ruling and each taking back is in the audit log, with what was ruled and not the note.

### Searching by hand

Once the connection has been tested, the Threat intelligence page has a search. It takes an IP
address, a domain such as `example.com`, or a web address that starts with `https://` or `http://`,
and shows what VirusTotal reported: whether engines flagged it as malicious or suspicious, how many
engines gave a verdict and what each said, the community's score, the categories it was given, what
else VirusTotal says (the owner and country of an address, the registrar of a domain, the title and
final address of a web address), and a link to its page on VirusTotal's own site.

A search is refused, and nothing is sent, for a private or other non-public address, a name that
only exists on a network of its own (`router`, `nas.local`, `printer.lan`, `box.test` and the like),
one of the home's own addresses on the internet, a web address with a username or password in it,
and anything that is none of these. The reason is shown in the search. A domain is judged by its
text alone: AresGate doesn't resolve it, so a search can't reach a device on the home network.

Only the host of a web address is kept with the search, not the rest of it, and its answer is kept
under the SHA-256 of the whole address, so the address itself is kept nowhere. Its query string is
sent, since it is part of what VirusTotal scans. A domain or web address that VirusTotal has never
analysed is shown as having no report yet, and AresGate doesn't ask VirusTotal to scan it.

A search that isn't answered from what was kept counts toward the same limits as the lookups above.
When it would go over one, or VirusTotal's daily count is used up, nothing is sent. If AresGate has
an answer kept for the subject, however old, the search shows it, and the report says why it wasn't
checked again. The same goes for a search VirusTotal didn't answer. With nothing kept, the search is
refused with the seconds to wait (HTTP 429, with a `Retry-After` header). A search that is answered
from what was kept says so in its report, with the time VirusTotal was asked.

### What is kept, and what the AI does with it

For each subject AresGate keeps one row: VirusTotal's last answer about an address, a domain or a web
address, and when it was asked about. A report keeps the counts of VirusTotal's last analysis (how
many engines call it malicious, suspicious, harmless or undetected), its community reputation score,
its country, and for an address the owner and number of the network it belongs to, plus the
categories and what else VirusTotal says of it. An answer with no report keeps only that. A newer
answer replaces the one kept, once the subject is asked about again (see What is kept, above).

The AI reads the reports of addresses as part of an incident's brief, and can look one up with its
reputation tool. Domains and web addresses are not read by the AI. The AI never asks VirusTotal
itself: its tools only read what is kept, so a question put to the AI spends no lookup. Each request
is logged with its address, or for a domain or web address its domain or host, and its outcome, and
is forgotten after 40 days, which is longer than the month the allowance counts over.

### Where this comes from, and what isn't tried

Taken from VirusTotal's documentation:

- The access levels and the usage rule are on
  [Public vs Premium API](https://docs.virustotal.com/reference/public-vs-premium-api), and where the
  key is found is on the [overview](https://docs.virustotal.com/reference/overview).
- The lookup is `GET /api/v3/ip_addresses/{ip}` with the key in the `x-apikey` header. The fields
  read are described in the [IP address report](https://docs.virustotal.com/reference/ip-info) and
  its [object](https://docs.virustotal.com/reference-link/ip-object), and the errors in
  [the errors page](https://docs.virustotal.com/reference/errors).
- A search of a domain is `GET /api/v3/domains/{domain}`, and of a web address
  `GET /api/v3/urls/{id}`, with the key in the same header. The docs describe the URL id as the URL
  identifier or the URL in base64 without padding. AresGate sends the SHA-256 of the address as the
  identifier, which keeps the whole address out of the request path in its log. That reading of the
  docs is inferred, not confirmed against the live service.

Worked out here, not in the documentation:

- A 404 (`NotFoundError`) is taken as no report for that address, domain or web address. The errors
  page says only that the resource was not found, and doesn't say what that means for one with no
  report.
- The links to VirusTotal's website (`/gui/ip-address/`, `/gui/domain/` and `/gui/url/`, the last with
  the SHA-256 of the address) are inferred from its site, not from these pages.
- The domain and web address fields (the registrar, the title, the final address and the times
  submitted) are read the same way as an address's, and one that isn't there is left out. The pages
  above don't show these objects' fields.
- The 15,000 a month is AresGate's margin, not a figure from VirusTotal.
- The last analysis date is read as a whole number of seconds since 1970 in UTC, which the object's
  example suggests but the page doesn't state.

Not tried against the live service: the answers, for addresses, domains and web addresses, are
tested against a stand-in built from these pages. An answer that doesn't match is logged as a failed lookup, with the reason, and tried again
later.

## AlienVault OTX

AlienVault OTX is a community of researchers who share _pulses_: a report of a threat with the
indicators that belong to it, such as the addresses a botnet used. It is the second
threat-intelligence integration, beside VirusTotal, in the same **Threat intelligence** group on the
Integrations page. Its address is fixed at `https://otx.alienvault.com`. Sign in to OTX, copy the
OTX key from your account's settings, and paste it into the card. The key is encrypted and is never
shown again. The card's **Lookup pace** sets how often the background loop asks about a new address:

| Pace               | A new address every | At most a day |
| ------------------ | ------------------- | ------------- |
| Gentle             | 90 seconds          | 1,500         |
| Balanced (default) | 30 seconds          | 5,000         |
| Fast               | 10 seconds          | 10,000        |

OTX publishes no limit on requests, so these are AresGate's own, kept so that a free community
service isn't asked for more than it can bear. A search by hand is held back only by the few
seconds between any two lookups and by the day's count. If OTX ever answers 429, nothing is sent for
five minutes, and the integration's page says so while it holds. That is never a sign the
connection is broken.

### What is asked about, and what comes back

Only internet addresses and domains are asked about, with `GET /api/v1/indicators/{IPv4|IPv6|domain}/{value}/general`
and the key in the `X-OTX-API-KEY` header. Web addresses are not sent, since they would go in the
request path and the API log keeps that. An address inside the home is never sent, the same as for
VirusTotal. Every address sent is shared with OTX, which is worth knowing before turning this on.

The answer says how many pulses name the address, the newest few of them, who owns the address and
where it is, and whether OTX lists it as safe. AresGate reads it as a judgement the AI and you can
overrule:

- An address OTX lists as safe is **clean**, whatever else names it.
- A pulse that also names a malware family, an adversary or an attack technique says more than one
  that only lists the address. Two such pulses, or five of any kind, make the address **malicious**.
- Any pulse makes it **suspicious**.
- No pulse makes it **unknown**, not clean. New attackers often have no pulse yet, and OTX only knows
  what researchers have shared, so an address with none is asked about again sooner.

The malware families, adversaries and tags the pulses name are kept as the address's categories,
and the pulse count, the newest pulse and what it names are kept as its details. OTX's reputation
score, which rises with bad behaviour, is kept negated so that it reads like VirusTotal's.

### What the AI does with it

The AI reads OTX's answer about each address of an incident beside VirusTotal's, under its own
heading, and its `reputation` tool shows it too. It is told that a pulse that only lists an address
is weak evidence, since researchers also list scanners and cloud ranges that did nothing wrong, and
to keep its confidence modest when OTX alone points at an address. That is what sends the decision
to the **Review** page (see [Review](ui.md)), where you agree or disagree, while a decision made
with several sources agreeing is listed as already made. How much waits for you is set under
**Settings > Review**.

On an incident's conversations, an address OTX has something to say about gets a chip beside
VirusTotal's, such as *OTX: 3 pulses, Mirai*, that opens the address's page on OTX. It draws the
address as a warning only when OTX's word is malicious, since a pulse that merely lists an address
is weak.

### Where this comes from, and what isn't tried

Checked on 2026-11-12 against OTX's
[external API reference](https://otx.alienvault.com/assets/static/external_api.html) (titled
"LevelBlue External API documentation", version 1, base `/api/v1`), which the code was first written
without, from public descriptions. The reference confirms:

- `GET /api/v1/indicators/IPv4/{ip}/{section}` and `/IPv6/{ip}/{section}` exist, with the sections
  general, reputation, geo, malware, url_list, passive_dns and http_scans. AresGate asks for
  `general`.
- `GET /api/v1/indicators/domain/{domain}/{section}` exists, with the sections general, geo,
  malware, url_list, passive_dns, whois and http_scans. AresGate asks for `general`.
- A 404 is documented for indicator lookups, which AresGate takes as no report.
- `GET /api/v1/users/me` (and `/user/me`) exist as the way to validate a key, which is what the
  connection test uses.

The reference also lists `/pulses/subscribed`, `/pulses/activity`, `/pulses/{id}`, `/search/pulses`
and a separate `/indicators/hostname/{hostname}/{section}`, none of which AresGate asks for.

What the reference does **not** state, so that it rests on OTX's public descriptions and has not
been checked against a live key: the `X-OTX-API-KEY` header name, a limit on requests (it gives
none), and the body of every answer (it lists only 200 and 404), so the `pulse_info`, `validation`,
`reputation`, `asn` and `country_code` fields are read as described elsewhere.

Worked out here, not in the documentation:

- OTX's pages give no rate limit, so the paces above and the five-minute wait after a 429 are
  AresGate's own.
- A 404 is taken as no report, the same as a pulse count of none.
- The `validation` entry whose source is `whitelist` or `false_positive` is read as OTX listing the
  address as safe, and the pulse fields `malware_families`, `adversary` and `attack_ids` as what a
  pulse names.
- The links to OTX's website (`/indicator/ip/` and `/indicator/domain/`) are inferred from its site.
- Every name is sent to the `domain` endpoint, subdomains included. The reference gives `rghost.net`
  as the example for `domain` and `otx.alienvault.com` for the separate `hostname` endpoint, and
  doesn't say whether `domain` answers a subdomain the same way. AresGate has not tried the
  `hostname` endpoint.

Not tried against the live service: the answers are tested against a stand-in built from these
descriptions, and any field that isn't what was expected is left out rather than guessed. An answer
that doesn't hold an indicator is logged as a failed lookup, with the reason, and tried again later.

## GreyNoise

GreyNoise listens on sensors all over the Internet and records who is scanning and attacking
everything at random. It is the third threat-intelligence integration, in the same **Threat
intelligence** group on the Integrations page, and it answers a different question from the others:
not whether an address is bad, but whether it is _background noise_. Most of the alerts a home
network raises are one of the thousands of addresses that probe every address, which is a reason to
take an alert less seriously, not more. Its address is fixed at `https://api.greynoise.io`.

### Plans

It works with every way of asking, which the card's **Account** and **Plan** settings choose:

| Setting                                 | What is asked                | What GreyNoise allows                     | What AresGate does                               |
| --------------------------------------- | ---------------------------- | ----------------------------------------- | ------------------------------------------------ |
| No account                              | The Community API, no key    | 10 lookups a day                          | At most 8 a day, a new address every 3 hours     |
| Free account (an API key)               | The Community API, with key  | 50 searches a week, shared with the Visualizer | At most 40 a week, a new address every 4 hours 15 minutes |
| Standard, Advanced or Elite subscription | The IP Lookup API            | Not published                             | A new address every 10 seconds                   |

Only an account made with a business email is given an API key: GreyNoise says accounts made with a
free email address, such as Gmail, have none, and for those **No account** is the choice. The key is
on the GreyNoise Visualizer's **API Key** page, under the account menu's **Workspace**, which also
shows the week's searches used. The key is encrypted and is never shown again.

The week's searches are shared with the Visualizer, so AresGate leaves ten of the fifty for you.
Its lookups are spread over the whole allowance instead of used at once, and an address already
answered is not asked about again until the answer is stale. If GreyNoise answers 429, which says
the allowance is used up, nothing is sent for an hour, and the integration's page says so while it
holds. That is never a sign the connection is broken. A test of the connection with an account's key
or none is one lookup of `8.8.8.8` and spends one of those lookups; a subscription's key is tested
with GreyNoise's ping, which asks about no address and counts as none. The connection is never
tested on a timer.

### What is asked about, and what comes back

Only IPv4 addresses on the internet are asked about, since GreyNoise's Community API takes no other,
with `GET /v3/community/{ip}` (or `GET /v3/ip/{ip}` for a subscription) and the key in the `key`
header. An address inside the home is never sent, the same as for VirusTotal. Every address sent is
shared with GreyNoise, which is worth knowing before turning this on.

The answer is one of three things, which AresGate reads as a judgement the AI and you can overrule:

- **A business service** (GreyNoise's RIOT dataset: public DNS, cloud and content providers) is
  **clean**, as is a scanner GreyNoise classifies _benign_, such as a known research scanner or
  search engine.
- **A scanner classified malicious** is **malicious**, and one it has seen scanning but not
  classified is **suspicious**.
- **Nothing** is **unknown**, not clean. An attack aimed at one network alone shows on none of
  GreyNoise's sensors, so an address it has not seen says little.

The classification, when it was last seen and the business service are kept as the address's
details. A subscription's answer adds when it was first seen, the actor and tags GreyNoise attaches,
the CVEs, whether it is a Tor exit or a VPN, its reverse DNS, and the owner, country and ASN. A plan
that holds fields back (GreyNoise answers 206 and lists them) gives a report of what it has.

### What the AI does with it

The AI reads GreyNoise's answer about each address of an incident under its own heading, and its
`reputation` tool shows it too. It is told that an address GreyNoise classifies malicious is mass
scanning or opportunistic exploitation aimed at everyone, so an attempt from it that was blocked or
failed is background and calls for a low severity unless the traffic shows it got in, and that
GreyNoise calling an address benign or a business service is not proof that what it did to this home
was harmless. That is how a flood of probes stops raising alarms while a targeted attack, which
GreyNoise has never seen, is not hidden by it.

On an incident's conversations, an address GreyNoise has something to say about gets a chip beside
the others, such as *GreyNoise: scans the internet, malicious*, that opens the address's page on the
GreyNoise Visualizer. It draws the address as a warning only when GreyNoise's word is malicious.

### Where this comes from, and what isn't tried

Taken from GreyNoise's [Community API](https://docs.greynoise.io/reference/getcommunityip) and
[Using the Community API](https://docs.greynoise.io/docs/using-the-greynoise-community-api) pages,
its [v3 API guide](https://docs.greynoise.io/docs/using-the-greynoise-api) and
[OpenAPI description](https://api.greynoise.io/v3/openapi.yaml), its
[account setup page](https://docs.greynoise.io/docs/setting-up-an-account) and its
[plans](https://www.greynoise.io/plans): the `key` header, the `noise`, `riot`, `classification`,
`name` and `last_seen` fields of the Community API, the 10 lookups a day without an account and 50
searches a week with a free one, that the free key shares them with the Visualizer, `GET /ping`, and
the `business_service_intelligence` and `internet_scanner_intelligence` sections of the IP Lookup
API.

Worked out here, not in the documentation:

- A subscription's lookup limits are not published, so the pace for it, the 8 a day and 40 a week
  margins, and the hour's wait after a 429 are AresGate's own.
- A 404, and a 200 that names neither noise nor a business service, are taken as no report.
- The Visualizer's page for an address (`/ip/` and, for a business service, `/riot/`) is inferred
  from the links in its examples.
- That `/ping` answers a subscription's key is read from its description; whether it answers a free
  key is not, which is why those are tested with a lookup.
- A plan that holds back the classification gives a scanner counted as suspicious, the same as one
  GreyNoise does not classify.

Not tried against the live service: the answers are tested against a stand-in built from these
descriptions, and any field that isn't what was expected is left out rather than guessed.

## NIST NVD

The National Vulnerability Database (NVD) is the US government's list of known software
vulnerabilities, each a CVE with a score for how severe it is. It is the fourth integration in the
**Threat intelligence** group, and it answers a different question from the others: not who is
attacking, but what the attack tried. It is asked about **CVEs, never addresses**: an alert that
says it tried an exploit of `CVE-2021-44228` is worth reading differently once the AI knows what
that is. Its address is fixed at `https://services.nvd.nist.gov`.

### Plans

An API key is optional, and the card's **API key** setting chooses whether one is sent:

| Setting                | What NVD allows              | What AresGate does                          |
| ---------------------- | ---------------------------- | ------------------------------------------- |
| Ask with an API key    | 50 requests in 30 seconds    | One lookup every 3 seconds at most          |
| Ask without a key      | 5 requests in 30 seconds     | One lookup every 10 seconds at most         |

NVD suggests waiting about six seconds between requests. A lookup is one request for one CVE, and
there are rarely more than a few a day, so even no key is plenty; with one the CVEs of a flood of
alerts are answered sooner. Ask for a key on NVD's
[request page](https://nvd.nist.gov/developers/request-an-api-key) with an organization name, an
email address and the organization type, and agree to its terms. NVD emails a link, good for seven
days, that shows the key once. A key belongs to one person or application and is not to be shared.
The key is sent in the `apiKey` header, so it is in no address and no API log entry, and it is
encrypted and never shown again.

If NVD answers 403, 429 or 503, which it does when a limit is reached, nothing is sent for two
minutes. That is never a sign the connection is broken. The connection is tested with one lookup
of `CVE-2021-44228`, by hand and on the periodic check, and it passes when NVD answers with a list
of CVEs. NVD says a key it doesn't know in a header named `message`, which the test shows.

### What is asked about, and what is kept

AresGate reads the CVE ids that recent incidents (the last 30 days) name in what their alerts say:
the summary, the signature and what a program reported (including the CVEs Wazuh's vulnerability
detector lists). Each is asked about once with `GET /rest/json/cves/2.0?cveIds=...`, the newest
incident's first, and nothing else is sent. Nothing is asked until the connection has been tested.
What NVD answers is kept in a table of its own, one row for each CVE:

- the **CVSS score**, its rating (None, Low, Medium, High or Critical) and its vector. The newest
  version of CVSS NVD gives is read, and the primary source's score when it has two;
- the **weakness** (the CWE ids) and a description in English;
- NVD's **status** (Awaiting Analysis, Analyzed, Rejected and so on) and when it was published;
- whether CISA's **Known Exploited Vulnerabilities** list has it, since when, and what CISA
  requires and by when. NVD carries this list, which is the nearest thing there is to knowing a
  vulnerability was used in the wild.

A CVE NVD has no record of is kept as unknown, which says little: a new one is recorded some time
after it is announced. How long an answer stands follows how it can change: a record with no score
or no record at all is asked about again after a day, a scored one after three days, and one on
CISA's list after two weeks, since it is not taken off.

### What the AI does with it

The AI reads what NVD says of the CVEs an incident names (up to eight) under its own heading, and
its `vulnerability` tool shows one. It is told that the CVSS score rates the vulnerability and not
this attack: a Critical CVE that was only probed, or that the device isn't running, is not a
Critical incident, while one on CISA's list has been used against real networks. An unknown CVE
says little and a Rejected one is not a vulnerability at all.

An incident's page lists the CVEs it names in a card of their own: the score and rating, an
*Exploited in the wild* badge for one CISA lists, what it is, and a link to the CVE at NVD. A CVE
that NVD has not been asked about yet says so. NVD asks that a service that shows its data says
that it **uses data from the NVD API but is not endorsed or certified by the NVD**, and the card
does.

### Where this comes from, and what isn't tried

Taken from NVD's [CVE API](https://nvd.nist.gov/developers/vulnerabilities) and
[Start Here](https://nvd.nist.gov/developers/start-here) pages: the address and the `cveIds`,
`resultsPerPage` and `hasKev` parameters, the `apiKey` header (case sensitive), the rate limits of
5 and 50 requests in a rolling 30 seconds and the six seconds NVD suggests between requests, that
an explanation of an error is in the `message` header and that a valid request can answer 200 with
no results, the shape of the answer (`vulnerabilities`, each with a `cve` holding `descriptions`,
`metrics`, `weaknesses` and the `cisa` fields), and the notice above.

Worked out here, not in the documentation:

- A 403, a 429 or a 503 is taken as a limit being reached, and nothing is sent for two minutes.
- A 404 whose `message` names the key is taken as a key NVD doesn't know. Any other 404 is a CVE
  NVD has no record of.
- Which CVSS score is read: the newest version, and the primary source's before a secondary one.
  A rating NVD does not give is worked out from the score with the bands CVSS defines.
- The pace of the lookups, how long an answer stands and the 30 days of incidents that are read
  are AresGate's own.

Not tried against the live service: the answers are tested against a stand-in built from these
descriptions, and any field that isn't what was expected is left out rather than guessed.

## Fingerbank

Fingerbank fingerprints devices. Asked about a hardware (MAC) address it answers with the make and
model the address most likely belongs to, the operating system and a score for how sure it is. It
is the first integration in the **Device intelligence** group of the Integrations page, and its
address is fixed at `https://api.fingerbank.org`. Create a free account on Fingerbank's website,
copy the API key from **My Account** and paste it into the card. The key is encrypted and is never
shown again, and is sent in the `Authorization` header, so it is in no address and no API log entry.

The Integrations page has a search at the top and a button for each kind of integration (Network
monitoring, Threat intelligence, Device intelligence), so a long list can be narrowed by what an
integration is called, what it provides or its kind.

### What is asked about, and what is kept

A device is asked about with `GET /api/v2/combinations/interrogate` and the hardware address as the
only thing in the body. Not its name, its traffic or its IP address. A device that made up its own
hardware address, as a phone does on Wi-Fi so it can't be followed from network to network, is
never asked about, since the address says nothing of what it is. Fingerbank says it keeps what it is
sent to improve its matching, and that it is never made public or shared.

The answer is kept with the device, so every later connection from the same hardware address
carries it and the device is not asked about again until what was said has gone stale: thirty days
for a device Fingerbank named, a week for one it had no match for, since its database grows. What is
kept is the most specific name ("Apple iPhone 16"), the path to it ("Phone, Tablet, or
Wearable/Apple iOS, macOS, and tvOS/Apple iPhone/Apple iPhone 16"), the maker, the operating
system, the score, when it was asked and why. It shows on the asset's page under **What it is**,
with the score in the bands Fingerbank gives (below 31 low, to 50 moderate, to 75 high, above that
very high), and as a flag on the asset's card in the list.

### Whose devices, and in what order

Your own devices are asked about first: the devices on your network, the newest first, since a new
device is the one worth knowing about. The card's **Devices in incidents and threats** setting is
**Only my own devices** until you change it. When it is on, the devices that a recent incident names
are identified as well, which includes machines on the internet side of the firewall, and comes
after your own. It sends their hardware addresses to Fingerbank too, so it is off until you allow it.

### The limit

The free key is limited to 600 requests an hour. AresGate keeps its own lookups to 550 an hour, at
least ten seconds apart, which leaves the rest for the connection check and for tests made by hand.
Reaching the limit is never an error: if Fingerbank answers 429, nothing is sent for five minutes
and AresGate carries on, and a device it has no match for is a 404, which is an answer, not a
failure. A key Fingerbank turns down (401) or has blocked (403) is shown on the card as a problem.
Fingerbank also blocks a client that uses more than one key from the same internet address, so use
one key for AresGate.

### Where this comes from, and what isn't tried

Taken from Fingerbank's [API v2 reference](https://api.fingerbank.org/api_doc/2.html), its page on
[how to use the API](https://www.fingerbank.org/usage/), its
[fair usage policy](https://www.fingerbank.org/fair-usage-policy) and its
[terms and privacy](https://www.fingerbank.org/privacy) page: the `interrogate` request with its
`mac` parameter, the Bearer `Authorization` header, the fields of the answer (`device`,
`device_name`, `manufacturer`, `operating_system`, `score`), the 401, 403, 404, 429 and 502 answers,
the score bands, the 250 requests a minute that every key is capped at, and that what is sent may
be kept.

Worked out here, not in the documentation:

- The reference lists the answer's fields but not whether `manufacturer` and `operating_system` can
  be null, so each is read as optional, and anything that isn't the expected shape is left out.
- The reference doesn't give the free key's hourly figure. The 600 an hour comes from the
  maintainer's own notes; the pages above say only 250 a minute.
- Fingerbank's usage page sends the request as `GET` with a JSON body, and the reference lists
  `GET` and `POST`, so `GET` is used, which keeps every request one that changes nothing here.
- The connection test asks about a hardware address that belongs to no device (the one RFC 7042
  gives for documentation) and takes either an answer or a 404 as the key being accepted.
- Only the hardware address is sent. Fingerbank can use a DHCP fingerprint, a host name and more
  for a surer answer; AresGate doesn't collect the DHCP fingerprint, and a host name is a personal
  detail, so the score of an answer from a hardware address alone is often low.

Not tried against the live service: the answers are tested against a stand-in built from the
reference.

## Setup instructions

Each integration's page has a **Setup instructions** button that opens the steps for getting what
its connections ask for: a user or key made in the product, the privileges or roles it needs and
the address to enter. They are written from the product's own documentation and source, and the
window lists the pages at its end:

| Integration | Written from |
| ----------- | ------------ |
| OPNsense | [API how-to](https://docs.opnsense.org/development/how-tos/api.html), [API](https://docs.opnsense.org/development/api.html), [local users and groups](https://docs.opnsense.org/manual/how-tos/user-local.html), the privileges in OPNsense's [core](https://github.com/opnsense/core/tree/master/src/opnsense/mvc/app/models/OPNsense) and [plugins](https://github.com/opnsense/plugins/tree/master/security) source, and Zenarmor's API pages |
| ntopng | [authentication](https://www.ntop.org/guides/ntopng/authentication.html#token-based-authentication), [settings](https://www.ntop.org/guides/ntopng/web_gui/settings.html), and the source of `add/ntopng/user.lua`, `create/ntopng/api_token.lua` and the user form's labels |
| Wazuh | [API](https://documentation.wazuh.com/current/user-manual/api/getting-started.html), [RBAC](https://documentation.wazuh.com/current/user-manual/api/rbac/configuration.html), [internal users](https://documentation.wazuh.com/current/user-manual/user-administration/rbac.html) and the default roles in Wazuh's source |
| CrowdSec | [local API authentication](https://docs.crowdsec.net/docs/local_api/authentication/) and [configuration](https://docs.crowdsec.net/docs/configuration/crowdsec_configuration/) |
| VirusTotal | [Public vs Premium API](https://docs.virustotal.com/reference/public-vs-premium-api), the [overview](https://docs.virustotal.com/reference/overview) for where the key is found, the [IP address report](https://docs.virustotal.com/reference/ip-info) and its [object](https://docs.virustotal.com/reference-link/ip-object), and the [errors](https://docs.virustotal.com/reference/errors) |
| AlienVault OTX | OTX's [external API reference](https://otx.alienvault.com/assets/static/external_api.html)                                                                                                                                                                                                                                                                                                                                                       |

A step marked **Not from the documentation** says what was worked out and why. These were
read, not run against every release, so the connection test is what tells whether a step worked.
The ones to know about:

- **OPNsense privileges.** OPNsense's documentation doesn't list what an API client needs. The
  list (*Lobby: Dashboard*, *Diagnostics: System Activity*, *Netstat*, *ARP Table*, *Logs:
  Firewall: Live View*, *System: Gateways*, *Services: Intrusion Detection*, the DHCP service you
  use and the CrowdSec and Wazuh agent plugins) is the privileges whose rules, in OPNsense's
  source, allow the calls AresGate makes. The Wazuh agent plugin's rules name `wazuh_agent` while
  AresGate asks `wazuhagent`, so whether that privilege alone is enough is not known.
- **OPNsense's key button** is in the API section of the user's page in one page of the
  documentation and a key button in the list of users in another; the window says both.
- **ntopng.** Its guide says where to generate a token (Settings, User, Edit, *User Authentication
  Token*) for the signed-in user. The role and the *Allow Alerts* flag a read-only client needs
  come from ntopng's user form and source, not from its guide. An administrator can make the token
  for another user with `create/ntopng/api_token.lua`, which the window shows.
- **Wazuh.** The pages found describe creating a user through the API and the `agents_readonly`
  role, but not the dashboard's Users tab or which button links the role to the user (the API
  call that does was tried). The indexer role is narrowed from Wazuh's read-only example to
  `read` on `wazuh-alerts-*` with no cluster permission, which was tried on OpenSearch, not on
  Wazuh's build of it.
  role, but not the dashboard's Users tab, and the indexer role is narrowed from Wazuh's
  read-only example to `wazuh-alerts-*`. If the indexer's test is refused, add `cluster_monitor`.
  That the API's and the indexer's certificates are not the dashboard's comes from Wazuh's pages
  on the API (default self-signed certificates, the `https` settings of `api.yaml`), on
  third-party certificates (the dashboard only) and on certificate deployment (`root-ca.pem`);
  the fingerprint command is plain OpenSSL, and that a certificate holds the addresses it was
  made with is read from the certificate tool's script.
- **CrowdSec.** The configuration page gives `api.server.listen_uri` as `host:port` but no
  default; `127.0.0.1:8080` is from other pages' examples.

The text is in `backend/app/integrations/guides.py`, one `Guide` for each integration with a
`Part` for each of its connections (a test requires every connection to have one), and reaches
the web app in the integration's `guide`.

## What AresGate will connect to

Every integration is reached the same way, and a few rules are not settings:

- **Only your own network.** The address must be a private one (`10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`, the link-local and unique-local ranges, and loopback only where the
  deployment allows it). A name is resolved once and the connection goes to that address, so a
  name that changes its answer afterwards can't send AresGate somewhere else. The one exception is
  [VirusTotal](#virustotal), which is on the internet at a fixed public address.
- **Never the cloud metadata addresses** (`169.254.169.254` and its relatives), even though they
  are link-local.
- **No redirects and no proxy.** A redirect is reported as the answer it is, not followed, so an
  integration can't bounce AresGate to another address.
- **Certificates are verified, and never skipped.** HTTPS addresses are checked against the
  system's trusted authorities, or in one of two other ways, chosen under **Certificate** on the
  integration's page. A product with its own certificate (OPNsense, Wazuh) needs one of them:
  - **The certificates this computer trusts.** For a certificate from a public authority, such as
    Let's Encrypt.
  - **A certificate authority I paste.** Paste the PEM certificate of the authority that signed it.
    It is accepted as OpenSSL's tools make it, even without a key usage extension (the checks on
    the signatures, the dates and the name are the same as for any other certificate).
  - **Only this exact certificate.** The SHA-256 fingerprint of one certificate, typed in or
    filled in by looking the certificate up (next section). Nothing else is accepted, even if it
    looks valid.

### Trusting the certificate a system presents

You don't need to know which of those to choose, or to find a fingerprint. On any integration's
page, under **Certificate**, click **Look up the certificate** (it works whichever way is chosen,
and needs only the address). AresGate connects, takes the certificate the system presents (nothing
is sent over the connection, so no key goes anywhere) and shows it:

- who it is for (subject and issuer), the names it lists, when it is good for, and whether it is
  **Self-signed** or **Expired**;
- its SHA-256 fingerprint, to compare with the one the system itself shows (OPNsense: **System,
  Trust, Certificates**; or, for a certificate file you have, `openssl x509 -noout -fingerprint -sha256 -in <file>`);
- the other certificates it sent with it, if any, which vouch for it;
- whether the way of checking chosen would accept it as it is, and, if not, why, in the words of
  the section below.

**Trust this certificate** pins it: the connection then accepts that exact certificate and no
other, whatever it is. That is the choice for a system that makes its own certificate, and it is
there for you to take even for one that has expired or names someone else, since the decision is
yours. Nothing is skipped: the fingerprint is compared before a request is sent, so a key never
goes to a system that is not the one trusted.

You rarely have to look for the button. When a test fails over a certificate, the failure says so
and has **Review the certificate** (on the connection's card, and in the report of the test), and
**Trust and test** there trusts the certificate, saves what is filled in and tests again. Wazuh
has two connections, the manager and the indexer, each with its own certificate: do it for each.

If a pinned system later presents a different certificate (it was renewed, or replaced, or
something else answers at that address), the test fails with "The certificate has changed", naming
both fingerprints, and **Review the certificate** shows the new one beside the same decision. If
you didn't change anything on the system, don't trust it.

### When a certificate that looks valid isn't trusted

A browser accepts a Let's Encrypt certificate that AresGate refuses with "unable to get local
issuer certificate" when the system **sends only its own certificate** (Let's Encrypt's
`cert.pem`) and not the certificate of the intermediate authority that signed it (`fullchain.pem`
has both). A browser fetches or remembers the missing one; OpenSSL, and so AresGate, doesn't.
OpenSSL words that the same as a certificate signed by an authority nobody here knows, so
AresGate connects once more, to look at the certificates the system presents (nothing is sent),
and says which it is, naming the authority:

- **Sent without the certificate that signed it.** Serve the whole chain on that system (with
  Let's Encrypt, `fullchain.pem` instead of `cert.pem`). Or, in AresGate, paste the missing
  authority's certificate under **Certificate**, **A certificate authority I paste**: the
  intermediate is enough, you don't need the root. The message gives the address the
  certificate itself names for it, if it names one. Trusting the certificate as it is (the
  section above) works too, and is the only choice for a certificate nothing vouches for.
- **Signed by an authority this computer doesn't trust.** The message says where the chain it
  sent ends. Paste that authority's certificate (or add it to the one pasted), or trust the
  certificate as it is.
- **Sent alone by an authority that doesn't say where to get its certificate.** Public
  authorities' certificates usually say, so this is probably an authority of the system's own,
  such as the one Wazuh's certificate tool makes for the indexer, and it is named in the message.
  Paste that authority's certificate or trust the certificate as it is; the `fullchain.pem` advice
  is for a public one.
- **Also named in words:** a certificate that vouches for itself, one that has expired (and
  when), one that isn't valid yet (check the clocks), and one made for other names than the one
  in the address, which are listed. Use one of them in the address, since a certificate for a
  name isn't accepted for an IP address, or trust the certificate as it is. A certificate that
  names nothing at all can only be trusted as it is (pinned). Every one of these messages ends
  with that way out, and the review shows the same words with the button below.

The image carries Wolfi's `ca-certificates-bundle`, and its smoke test fails if Python finds no
certificate authority in it (`python -m app.cli trust-store` shows how many).

## Testing

**Save and test** keeps the settings and then makes the product's own harmless read request,
such as OPNsense's firmware status or CrowdSec's decisions list. The result says what answered
and what it found, or what went wrong in words: the wrong key, an unreachable address, an
untrusted certificate, a redirect, a timeout. **Test connection** repeats the test on what is
saved; it is turned off while there are unsaved changes, because it can only test what is saved.

Secrets are write-only. They are sealed with the app secret key
([operations.md](operations.md)) as soon as they are saved, and no page or API returns one:
after saving, the field says "Saved", and leaving it empty keeps the saved value.

**Disconnect** asks first, then forgets the address and the secrets. The API log stays.

### What a refusal means

HTTP 401 and 403 mean different things in each product, so the test (and the status page, which
shows the same sentence for a collector) says what that product's answer means:

| Product | 401 | 403 | Read in |
| --- | --- | --- | --- |
| OPNsense | The key and secret aren't known (`Authentication Failed`). | The key and secret are right, but the user's privileges don't include the page asked for (`Forbidden`). The message names the page. | [`ApiControllerBase.php`](https://github.com/opnsense/core/blob/master/src/opnsense/mvc/app/controllers/OPNsense/Base/ApiControllerBase.php), `beforeExecuteRoute` |
| ntopng | The user is signed in but isn't granted the capability (`NOT_GRANTED`, rc -3): alerts need the capability to see them, and a capture the permission to download PCAP files. A login it refuses is redirected to its login page (302) instead. | A user whose allowed interface doesn't exist. | [`rest_utils.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/modules/rest_utils.lua), [`flow/alert/list.lua`](https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/get/flow/alert/list.lua), [`HTTPserver.cpp`](https://github.com/ntop/ntopng/blob/dev/src/HTTPserver.cpp) |
| CrowdSec (local API) | Not used for a bouncer key. | `access forbidden`: the bouncer key isn't known, which is how it refuses a wrong one. A bouncer has no permission to lack. | [`api_key.go`](https://github.com/crowdsecurity/crowdsec/blob/master/pkg/apiserver/middlewares/v1/api_key.go), whose own comment asks whether it should be 401 |
| Zenarmor | Said as before: it didn't accept the credentials, or the user isn't allowed. | The same. | Not read: its documentation couldn't be reached when this was written. |

The Wazuh indexer has had its own wording since it was added, and the services on the internet
say what their own documentation says of a key they refuse.

What is **inferred**, not read in a product's own words: that the OPNsense 401 also covers a key
whose user was removed or disabled (the source only says the check failed), that a deleted
CrowdSec bouncer is refused the same way as a mistyped key (its key is looked up by hash), that
a CrowdSec bouncer has no permissions of its own (the middleware has none to check), and that
the ntopng 403 for an allowed interface that is gone is the one a user with a token meets, since
the source shows it at sign-in. None of it was tried against a running OPNsense, ntopng or
CrowdSec: no Docker was available where this was written. The tests use stand-ins that answer
as the source above does, so please open an issue if a real one answers differently.

## The API log

Each integration's page ends with the requests AresGate made to it: the time, the method, the
path, the status, how long it took and, if it failed, why. It can be filtered by result, method,
connection and time, and shows older requests on request.

- Secrets and query strings are never recorded, only the path.
- What the other system answered is untrusted text, so it is only ever shown as plain text.
- Requests are deleted automatically after `ARESGATE_API_LOG_RETENTION_DAYS` days (30 by
  default; see [`.env.example`](../.env.example)).

The collectors that read from these systems on a schedule use the same recording client, so what
they ask shows up here too. The page's **Collection** card says how each of those jobs is doing:
when it last ran, how long it took, when it runs next and, if it failed, why
([operations.md](operations.md#the-collector-worker)).

## How accurate this is

The requests follow each product's official API documentation, and the tests run against
stand-ins that behave as the documentation describes. They have not all been run against a live
OPNsense, Zenarmor, ntopng, Wazuh or CrowdSec. If a product answers differently from its
documentation, the test says what it got, and the API log shows the request. Please open an issue
with that.
