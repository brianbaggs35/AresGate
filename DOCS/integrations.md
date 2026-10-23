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

**Zenarmor** has an API of its own, on a port of its own, that takes a key made in Zenconsole
(register the firewall there, enable the API and make a key). It has its own switch on the
OPNsense page, **Use Zenarmor API**, with its own address, user and key, and its own certificate
settings. Leave it off if you don't use Zenarmor.

**Suricata** has no API outside OPNsense: it is the intrusion detection plugin, and it appears
under Services. **CrowdSec** on OPNsense is read the same way. A CrowdSec that runs anywhere
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
