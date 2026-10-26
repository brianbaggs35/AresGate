# Integrations

An integration is a system AresGate watches your network through. AresGate only ever reads from
them: it never changes their settings. Open **Integrations** in the menu to see one card for each,
with what it provides, whether it is connected and when AresGate last reached it. Click a card to
connect it, change its settings, test it or disconnect it.

| Integration | What it gives AresGate | How it connects |
| ----------- | ---------------------- | --------------- |
| OPNsense | Health, interfaces and traffic, gateways, the firewall log, ARP and DHCP, and the services that run on it: Suricata, CrowdSec, OpenVPN, WireGuard, IPsec, Unbound, Dnsmasq, Kea, the ntopng and Wazuh agent plugins, and Zenarmor | API key and secret |
| ntopng | Live traffic: hosts, flows and throughput | Authentication token, or user name and password |
| Wazuh | Alerts and agent health from the manager, and the alert history from the indexer | Two connections, each with a user name and password |
| CrowdSec | The ban decisions CrowdSec has made | A bouncer's API key |

Each card's page starts with the steps to get what it asks for, taken from the product's own
documentation, and a link to that documentation. The steps below are the same ones.

## OPNsense, and everything that runs on it

Suricata, CrowdSec, OpenVPN, WireGuard, Zenarmor and the rest are plugins of OPNsense, and
OPNsense's API reaches all of them with the one key. So they are not separate integrations:
connect OPNsense once, and testing the connection finds which are installed and running. They are
listed under **Services** on the OPNsense page, each with its state (running, stopped, not
installed, or not allowed for the key's user), and each can be switched off if you don't want it
read. The card on the list shows the ones in use.

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
  around it (`payload`, `packet` and the like), which stay on the firewall.
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
fill the list; each shows on the Collection card with its own state.

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

**Zenarmor** has an API of its own, on a port of its own, that takes a key made in Zenconsole
(register the firewall there, enable the API and make a key). It has its own switch on the
OPNsense page, **Use Zenarmor API**, with its own address, user and key, and its own certificate
settings. Leave it off if you don't use Zenarmor.

**Suricata** has no API outside OPNsense: it is the intrusion detection plugin, and it appears
under Services; its alerts are read as above. **CrowdSec** on OPNsense is read the same way. A CrowdSec that runs anywhere
else (a Raspberry Pi, a server) is the separate **CrowdSec** integration below.

## ntopng

1. In ntopng, edit the user AresGate will use and generate its **User Authentication Token**.
2. Choose **Authentication token** and paste it, or choose **Username and password** to use HTTP
   basic authentication instead.
3. The **Interface ID** is the `ifid` in ntopng's addresses. The first interface is usually `0`.

ntopng answers a login it refuses by redirecting to its login page. AresGate doesn't follow
redirects (see below), so a refused token shows up as "redirected to its login page".

## Wazuh

Wazuh has two connections, each with its own address and sign-in:

- **Manager API** (port 55000): create an API user for AresGate in the dashboard (Server
  management, Security, Users) with a read-only role, rather than using the administrator.
- **Indexer** (port 9200): create a user that may read the `wazuh-alerts-*` indices, rather than
  using `admin`.

Both use HTTPS with a self-signed certificate in a default install, so see the next section.

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
  own logs) and `cscli` (a ban someone typed in). The community blocklist (`CAPI` and the lists you
  subscribed to) is tens of thousands of addresses that attacked other people, and is left out so
  it doesn't bury the ones that attacked you.
- **When.** The local API gives no time for a decision, so an event is dated by the run that first
  saw it, which is within a minute of when it was made. A ban seen before is not stored again,
  however long it has lasted, and if its time runs out and CrowdSec bans the address again it is
  a new decision with a new number and is stored again.
- **Ranges.** A ban of a whole range (`203.0.113.0/24`) is kept with its summary, but has no
  source address, because an event's address is one address.
- **Alerts aren't read yet.** The alerts behind the decisions, with the events that made them, need
  a machine login (`cscli machines add`) rather than a bouncer's key, so they come later.
- **Not tried against a live CrowdSec.** The answer's shape is taken from CrowdSec's documentation
  and source and tested against a stand-in; if your version answers differently, the Collection
  card says so and the API log shows the answer.

## What AresGate will connect to

Every integration is reached the same way, and a few rules are not settings:

- **Only your own network.** The address must be a private one (`10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`, the link-local and unique-local ranges, and loopback only where the
  deployment allows it). A name is resolved once and the connection goes to that address, so a
  name that changes its answer afterwards can't send AresGate somewhere else.
- **Never the cloud metadata addresses** (`169.254.169.254` and its relatives), even though they
  are link-local.
- **No redirects and no proxy.** A redirect is reported as the answer it is, not followed, so an
  integration can't bounce AresGate to another address.
- **Certificates are verified.** HTTPS addresses are checked against the system's trusted
  authorities. A product with its own certificate (OPNsense, Wazuh) has two ways to be trusted,
  under **Certificate** on its page:
  - **Pasted authority.** Paste the PEM certificate of the authority that signed it.
  - **Pinned fingerprint.** Click **Look up the certificate**, compare the SHA-256 fingerprint it
    shows with the one in the product (OPNsense: **System, Trust, Certificates**), then click
    **Trust this certificate**. The connection then only accepts that exact certificate.

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
