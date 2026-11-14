# Changelog

Every release's notes are here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- **More from ntopng.** Five new collectors. **Application protocols** keeps the bytes of each
  protocol (DNS, TLS, streaming) the interface and the 40 busiest hosts use, as metrics, so the
  baselines can learn what a device normally talks. **Suspicious flows** keeps the 100 active flows
  with the highest score as events of their own kind, to match an alert with the flow behind it.
  **Interface, network, device and system alerts** become notices, which are never incidents.
  **Alert counts** keeps how many alerts there were of each severity and kind. **Host details**
  keeps each busy host's operating system, network, country and JA4, HASSH and TCP fingerprints,
  and the analyst can ask for them (`host_details`). See
  [ntopng](DOCS/integrations.md#application-protocols), which says what could only be inferred.
- **Wazuh vulnerabilities and each machine's inventory.** Two new collectors read the indexer's
  `wazuh-states-*` indices every 15 minutes. **Vulnerabilities** keeps each flaw Wazuh found as an
  event (the CVE, how serious, the package and the machine), once, when it is first seen; these
  are never part of an incident. **Inventory** keeps each agent's operating system, the ports that
  listen and the software installed, and lists a machine's network cards as devices, so the ARP
  table and the agent are one device. The analyst can ask about them (`open_ports`,
  `installed_software`, `host_vulnerabilities`, and `device` now says what a machine runs). The
  indexer user also needs read on `wazuh-states-*`. The manager's inventory endpoints are going
  away in Wazuh 5, which is why this reads the indexer. See
  [Vulnerabilities and inventory](DOCS/integrations.md#vulnerabilities), which says what could
  only be inferred.
- **Alerts now tell you when a collector goes quiet.** A collector that has not worked for
  fifteen minutes (or three of its own intervals, if that is longer) is told to every destination
  that is on, once for each stretch of silence, with when it last worked and what its last attempt
  said, and again when it works. It follows quiet hours and is not held back by the limit on
  messages an hour. A stopped worker still cannot alert. See
  [When a collector goes quiet](DOCS/alerts.md#when-a-collector-goes-quiet).
- **An Incident response page, right under Incidents in the menu.** It says in one sentence
  whether any incident still waits for a response, then lists the incidents of the last 24 hours,
  7 days or 30 days in the one group that says what was done about each: **needs a response**
  (going on and nothing stops it, only some of its addresses banned, or back after its ban
  ended), **banned**, **turned away** by the firewall or Suricata, **ban ended**, **closed
  without a response** and **nothing to block**. Only incidents of medium severity or higher count,
  and not those you called not suspicious or low priority or dismissed. It says what it cannot see
  when CrowdSec or OPNsense isn't connected. On a phone it is behind More, so the bar keeps Review.
  See [The Incident Response page](DOCS/operations.md#what-was-done-about-an-incident).
- **A Retention page in Settings, with a size limit for the database.** It starts switched off,
  and while it is off each kind of data is kept for the time of its own setting, as before.
  Switched on, you choose one number of days (30 by default) for events, measurements, the API
  log, the record of AI requests and the log of alerts sent, or keep everything forever with no
  age limit at all. You can also limit how big the database may get: when it is over, the oldest
  weeks of events and measurements are dropped, a whole table at a time and checked every fifteen
  minutes, until it is under 95% of the limit. Nothing that arrives is refused because of the
  limit, the week being collected and everything else is never touched, and the page says so when
  it is over with nothing more it may remove. See
  [Retention and the size of the database](DOCS/operations.md#retention-and-the-size-of-the-database).

- **Raw packets from ntopng, on a device's page.** The **Packets** card under a device's traffic
  has ntopng listen to the device's address for 5 to 30 seconds and shows what it saw: for each
  packet when it came, who sent it to whom with the ports, the protocol and the flags of a TCP
  segment, how big it was and its first bytes. Nothing of the capture is kept or sent to an AI, it
  is in the audit log with the host it was about, and only one runs at a time. The user AresGate
  signs in to ntopng as needs ntopng's permission to download PCAP files. See
  [Packets](DOCS/integrations.md#packets-of-a-host).

### Changed

- **Wrong passkey answers and wrong passwords are counted apart, so neither locks the other
  kind of sign-in out.** Before, they shared the address's count, so one person's wrong
  passwords could lock a household member's passkey out, and the other way around. Now a locked
  address still lets a right passkey in, and a locked passkey count still lets the password in.
  A sign-in challenge that ran out is no longer counted at all. Nothing counts against an
  account, as before. The reasoning is in
  [Security](DOCS/security.md#how-it-is-hardened-today).
- **The button on the Interfaces page that looks for what your programs report now says Find
  interfaces,** not Find feeds, so it says what you are looking for.
- **The connection tests and the status page now say whether OPNsense, ntopng or CrowdSec
  refused the sign-in or the user.** Each uses 401 and 403 in its own way, and the one sentence
  that covered both hid which it was. OPNsense says whether the key and secret are wrong or the
  user lacks the privilege for the page (and names the page), ntopng says the user isn't granted
  the capability or has an allowed interface it doesn't have, and CrowdSec says its bouncer key
  isn't known. Zenarmor keeps the one sentence, since its documentation couldn't be read. The
  official sources are listed in
  [What a refusal means](DOCS/integrations.md#what-a-refusal-means).

### Fixed

- **A busy NVD, OTX, GreyNoise or Fingerbank is no longer reported as a failed connection with a
  bare "HTTP 503".** Testing one of them now asks again after three seconds when it answers
  502, 503 or 504, and if it is still down says so: that it is unavailable, that this is on its
  side and not a problem with the key or AresGate, and that AresGate asks again on its own.

## 0.1.6

### Added

- **Threat hunter findings you can decide on, and the incidents it flagged.** A finding now says
  what it rests on (the facts it was shown, a line each), how to check it yourself and what would
  make it harmless, where the AI had enough to say. The hunter also reads the attacks across two
  devices, and is told to follow up on what looks serious. An incident that its last run names in
  a finding of medium or higher is **flagged** on its card and its page, listed on the Threats page
  and found by `hunted:yes` in Incidents. It is the hunter's opinion, and changes nothing about the
  incident. See [Agents](DOCS/agents.md#what-a-run-tells-you).
- **CI clears the caches nobody needs.** A new workflow deletes a pull request's caches when it is
  closed, and each Monday any that a pull request left and nothing has used for 3 days, so they
  don't crowd out the ones master's builds need. See [Development](DOCS/development.md#ci-caches).
- **Connecting OPNsense switches off the services that aren't running.** The first time the
  connection works, the services it finds installed but stopped are switched off, the test says
  which, and the form shows them off, so AresGate doesn't try to read what isn't there. Switch one
  back on whenever you like: later tests leave your choice alone. See
  [Integrations](DOCS/integrations.md#opnsense-and-everything-that-runs-on-it).
- **Zenarmor needs a paid subscription, and the setup says so.** The Zenarmor part of the OPNsense
  setup guide and [Integrations](DOCS/integrations.md) now say that Zenarmor lists its API as a
  feature of its paid editions, so the free edition may refuse the connection, and that leaving
  it off loses nothing else.
- **A guide to a quieter Threats page.** [Threats](DOCS/threats.md#if-it-is-still-too-noisy) now
  lists, in order, what to change when the page holds more than real attacks: how sure it has to be,
  the AI, what you tell it about your network, what you decide of a kind and what you answer on
  the Review page.
- **Notice when a quiet kind turns loud.** AresGate keeps what a kind of incident was like when
  the AI judged it: its stages of an attack, the destination ports, which of your devices it
  touches and how many addresses are behind it. When the incidents of it that are going on come to
  more (a new stage, a port or device a small kind never touched, or three times as many
  addresses), the kind is marked **Changed since judged**, its page says what changed, and the AI
  is asked about it again at the next opportunity your usage level allows, told what changed. A
  kind you called stays yours and is not judged again, but its page says it changed. See
  [Threats](DOCS/threats.md#when-a-kind-changes-after-it-was-judged).
- **Learn from your verdicts.** When you keep closing a kind of incident as not suspicious, low
  priority or dismissed (at least 5 of the incidents you decided, 4 in 5 of them), the Threats page
  and the kind's page offer **Always background?** with the numbers that led to it and how many
  incidents it would move. The other way round, a kind the AI set aside that you keep taking up or
  disagree with is offered **Never set aside?**. Nothing is ever done without your click, **Not
  now** is remembered until you have decided twice as many incidents of the kind, and a kind that
  has had a chain of stages in it is never offered to be set aside. What you decided of a kind is
  also told to the AI when it judges it. See
  [Threats](DOCS/threats.md#learning-from-what-you-decide).

### Changed

- **Trusting something, and giving a verdict, is faster.** Saying that an address, a program or an
  alert is safe, or a real threat, judges the incidents it can make a difference to again, and on
  a network with thousands of incidents that is what made it slow. Those incidents are now read and
  written in batches, one whose signals are judged just as they were is left as it is, and what a
  signal is about is worked out once however many decisions you have. Trusting a device on a
  network with 2000 incidents took about 4.9 seconds and now takes about 2.3. What is said of an
  incident is unchanged.
- **The dashboard loads faster.** The alerts and blocked connections of a window were counted in
  one pass over the stored events, and the window before it, for the comparison, in a second;
  the alerts needed a third to count the repeats. Each is now counted in a single pass. On a
  network with 2.2 million events in 15 days, the 24 hour dashboard took about 420 ms to work
  out and now takes about 320, and the 7 day one went from about 1.8 s to 1.5 s. The numbers are
  the same as before. The rest of the time is the other questions the page asks of the events,
  which each read the window once.

### Fixed

- **Fingerbank, OTX and NVD are no longer reported as "not a private network address".** The
  test you press reached them correctly, but the check AresGate repeats every five minutes looked
  for them on your home network, so their status turned to failed and said, for example, that
  api.fingerbank.org "isn't a private network address". Every service on the internet is now
  checked at its own address, like everywhere else.

## 0.1.5

### Added

- **Get alerts by email.** A new **Mail server** card on the **Alerts** page takes the settings
  of your email provider's server, or one on your network: its name, how the connection is made
  (STARTTLS, SSL or none), the port, the user name and password it needs and the address the
  emails come from. The password is encrypted and never shown again, and a user name and password
  are only sent over an encrypted connection. **Add destination** now offers **Email** beside
  Discord: give it an address and it has its own rules, a test message, a sample alert and a place
  in the delivery log, like a Discord channel. An email's subject is the incident's title with
  `[AresGate]` in front, and it can't be changed after it is sent. See
  [Alerts](DOCS/alerts.md#setting-up-email).
- **Know how severe a vulnerability is with NIST NVD.** A new **NIST NVD** card in the **Threat
  intelligence** group takes an API key (optional, encrypted and never shown again) for the
  National Vulnerability Database. When an incident's alerts name a CVE, AresGate asks NVD about
  it in the background, one CVE at a time and well inside NVD's limits (5 requests in 30 seconds
  without a key, 50 with one), and keeps its CVSS score and rating, the weakness, what it is and
  whether CISA has seen it exploited in the wild. Only the CVE is sent, never an address. The AI
  reads it with the incident, and is told that the score rates the vulnerability and not the
  attack, and has a new `vulnerability` tool. An incident's page lists the CVEs it names, with an
  *Exploited in the wild* badge, a link to NVD and the notice NVD asks for. See
  [NIST NVD](DOCS/integrations.md#nist-nvd).
- **Know what each device is with Fingerbank.** A new **Fingerbank** card in a new **Device
  intelligence** group of the Integrations page takes the API key from your Fingerbank account
  (encrypted and never shown again). AresGate then asks Fingerbank, in the background, what each
  device on your network is from its hardware address, your own devices first and the newest on
  the network first, and keeps the answer with the device: its make and model, its operating
  system and how sure Fingerbank is. Every later connection from the same hardware address carries
  it, and a device is only asked about again once what was said has gone stale. It shows on the
  asset's page under *What it is* and as a flag on its card. Only the hardware address is sent,
  and never one a device made up for itself. The card's *Devices in incidents and threats*
  setting, off until you turn it on, identifies the devices that incidents name as well. The free
  key's limit of 600 requests an hour is kept to, and reaching it is never an error. See
  [Fingerbank](DOCS/integrations.md#fingerbank).
- **Tell background noise from an attack with GreyNoise.** A new **GreyNoise** card in the
  **Threat intelligence** group takes the API key of a free account or of a Standard, Advanced or
  Elite subscription (encrypted and never shown again), or none at all: the free Community API
  allows 10 lookups a day without an account. AresGate asks, in the background, whether each
  internet address an incident names is one of the many that scan every address, or belongs to a
  common business service, spread over the allowance of the plan (50 searches a week on a free
  account, of which ten are left for you) and paused for an hour if GreyNoise says it is used up.
  The AI reads the answer beside VirusTotal's and OTX's and is told that a blocked or failed attempt
  from a mass scanner is background and calls for a low severity, while an attack GreyNoise has
  never seen is not hidden by it. The incident's conversations show it with a link to the address on
  GreyNoise. See [GreyNoise](DOCS/integrations.md#greynoise).
- **Search and filter the integrations.** The Integrations page has a search for what an
  integration is called or what it provides, and a button for each kind of integration, so the
  list is easy to narrow as more are added. Every card now says what kind it is, including the
  ones that watch the network.
- **See every device that connected, with the Devices page.** A new **Devices** place in the menu
  lists every address that took part in a connection your programs reported over the last week:
  your own devices, other private addresses and the ones on the Internet, with how many connections
  were made to each and by each, the ports they used, when it was last seen, the incidents it is in
  and what threat intelligence and Fingerbank say of it. Search by address or name, narrow to a
  kind of device or to those in an incident, and open one for its page: each connection with its
  source, destination, port and protocol, the events it was in, and links to its incidents, the kind
  of threat and the attack chain. The count is of events your programs reported, not every packet.
  See [Devices](DOCS/ui.md#devices).

### Changed

- **Python 3.14.10.** The project's own pin, used when you work on it without the container, moves
  from 3.14.8 to 3.14.10. The container is unchanged: it installs the 3.14 that Wolfi ships.

## 0.1.4

### Added

- **Ask AlienVault OTX about the addresses in an incident.** A new **AlienVault OTX** card in the
  Threat intelligence group of the Integrations page takes the OTX key from your account (encrypted
  and never shown again) and a lookup pace, gentle, balanced or fast. AresGate then asks OTX, in the
  background and at that pace, which community threat reports name each internet address or domain
  an incident involves, and what they say it is part of: a malware family, an adversary or an attack
  technique. The AI reads that beside VirusTotal's answer, and is told that a bare listing is weak
  evidence and to keep its confidence modest when OTX alone points at an address, so that call
  waits on the Review page while one several sources agree on is listed as already made. OTX
  publishes no rate limit, so AresGate paces itself and stops for five minutes if OTX answers that
  it is asked too much. Each address on an incident shows what OTX says of it, with a link to read
  the reports. Only addresses on the internet and domains are sent, never your own. See
  [AlienVault OTX](DOCS/integrations.md#alienvault-otx).
- **See what was said on the wire.** An incident has a new section, *What was said on the wire*,
  that shows what the firewall's intrusion detection read of the connections: the certificate a
  server showed (who it is for, who vouched for it, whether it signed itself or has run out, how
  the connection was encrypted), a web request sent without encryption with its headers, the names
  that were looked up and what came back, the banners of an ssh login and the start of the packet
  that set an alert off, as text and as bytes. It sits in panels, so a page is not long until you
  open one, and is left out when nothing was read. A few plain words at the top say what stands
  out, such as a login that went over plain web traffic, a certificate that has run out or a way
  of encrypting that is out of date. The analyst is told the same, and that many cameras, doorbells
  and other home devices sign their own certificates, so one that is only a camera calling its
  service is not read as an attack. A password, a cookie or a key is never kept: the value of such
  a header is replaced, and the start of a packet that looks like it carries a login is not kept at
  all. `ARESGATE_KEEP_PACKETS=false` keeps no part of a packet. See
  [What was said on the wire](DOCS/threats.md#how-it-travelled-and-what-it-was).
- **Review what the AI decided.** A new **Review** page in the menu lists what the AI called an
  incident, or a whole kind of incident, that would change what you see, with how sure it is, why
  and what it would do, and you click **Agree** or **Disagree**, with a reason if you like. A
  decision that waits for you counts only if it raises an alarm, so nothing is set aside on the
  AI's word alone. **Settings > Review** chooses how much waits: everything (the default), only
  what the AI is unsure of (with how sure it has to be), or nothing, when the AI decides on its own
  and the page still lists it. The AI is told what you disagreed with, and why, the next time it
  decides (and that can be turned off), and once you have agreed with 95% of 20 answers the page
  says it could be left to decide alone. The menu has a number for what waits, the dashboard says
  so, and an incident or kind shows where your review stands. See
  [Reviewing what the AI decided](DOCS/threats.md#reviewing-what-the-ai-decided).
- **Say what each device is, and see what an attack went through.** The page of every asset has a
  new *What is it?* card where you pick a kind (a router, a camera, a laptop, a smart-home
  device and so on, from a list that is grouped into the pieces of the network and the things
  around the home) and say in your own words what it is for. It shows on the Assets list with its
  own icon, you can filter the list by kind or by what you have not classified, and where a device's
  name or maker suggests a kind it is offered, never applied. An incident has a new section under
  *How it travelled*, *What it travelled through*, that lists the devices the attack went through or
  touched, in the order it met them, as the Assets page lists them: the firewall it crossed, the
  device it was about and any other device that turned up. A device you have not classified asks
  for it. What you said goes to the AI analyst too, so it reads a camera that calls a stranger
  differently from a laptop that browses. See [Assets](DOCS/ui.md#assets).
- **Blocked connections, by which way they went.** The dashboard has a new card under the charts
  that sorts what the firewall refused into the internet knocking, your own devices being turned
  away and one network of yours reaching another. It lists the ports the internet tried most and
  the devices of yours that were refused most, each with a link to the log lines. A device that is
  refused again and again is what a program gone wrong, or a taken-over machine, looks like from
  the firewall.
- **Trust: tell AresGate that something is fine.** A new **Trust** page lists what you have said
  is safe (or only low priority), with what each decision has kept from raising an alarm, and a
  page for each decision where everything about it can be changed or it can be taken back. A
  decision holds for every program at once: an alert that OPNsense and Wazuh both reported is one
  alert, so trusting its address quiets it whichever said it. A **Trust** button next to an incident's
  address (and each outside end of its conversations) asks what to trust, narrowest first (only what
  your camera sends to its cloud, only that alert, or everything about the address), and judges the
  incident again at once. The AI suggests what it is sure is nothing to worry about, and the
  assistant and the agents learn the *trusted* lookup. See [Trust](DOCS/trust.md).

- **Attacks across two devices are one attack.** An exploit aimed at a device on your network and
  that device calling out soon after are two incidents, about two different outside addresses.
  AresGate now links them into a chain by the device and the time between them: a link is *seen*
  when what the device sent is itself a sign it was taken over (a beacon, a command server), and
  *inferred*, and labelled as a guess, when it only called out. Nothing is linked without an exploit
  aimed at the device. A chain is a threat, is listed at the top of Threats, and has a page that
  draws the steps in order with the evidence behind each, an alert two programs reported counted
  once and shown with the programs that saw it. Each incident that is a step says so and leads to it.

- **How it travelled, what it was, and counted once everywhere.** An incident now draws the path an
  attack took from the internet through each program that saw it (the firewall, the intrusion
  detection system, the traffic monitor, the agent on the device) to the device, with what each did
  about it, without sending a probe into anyone's network. Addresses that no program named are
  given the name their owner gave them (marked *Name from DNS*; turn it off with
  `ARESGATE_REVERSE_DNS=false`), a conversation says in plain words what it was for, and where
  Suricata kept the packet its first bytes are shown as a dump. An alert that two programs reported
  is now matched even when one logged the reply instead of the request, and the Logs page says
  which other programs reported each alert, so what is counted once everywhere shows who saw it.
  The assistant and the agents learn two lookups: *who_is* and *attack_chains*.

### Fixed

- **Disconnecting an integration takes its collectors off the Status page and the dashboard at
  once.** They went on showing as working, and counted on the dashboard, until the worker next
  looked, or until you opened Status and refreshed it by hand. What the disconnected collectors
  had reported is now removed in the same step as the connection, so only a disconnect that
  worked changes the counts, and a run that was in flight when you disconnected no longer leaves a
  record behind.
- **Choosing a program on the Logs page no longer changes its number.** The counts under the search
  box were of the newest 50,000 events that matched, so choosing ntopng, say, narrowed the search
  and the number grew to the newest 50,000 of ntopng's own. They are now of everything that
  matches, and only the chart is of the newest 50,000.
- **The readout of a day on the AI usage chart no longer hangs below the chart.** Pointing at a day
  that took very little put the readout half below the chart's foot, where it was cut off or under
  what comes next. Every chart's readout now moves up or down just enough to stay inside the chart.

## 0.1.3

### Added

- **Mission control for the agents.** The top of the Agents page now treats them as one team: it
  says whether anything needs you (or that all is quiet, or how many agents are at work), shows the
  latest daily briefing, and lists the most serious findings of all the agents, each leading to the
  agent that raised it.
- **Three new agents.** The *Daily briefing* reads what the other agents reported, the open
  incidents, what changed at the firewall and how the integrations are doing, and writes one short
  report a day. The *Incident investigator* looks into your most serious open incidents as an
  analyst would and says what happened and what to do. The *Anomaly watch* learns what is usual at
  your firewall from the week before and tells you when the last day is not.
- **A new lookup, `what_changed`**, for the agents and the assistant: how the last hours at the
  firewall compare with the days before, which ports were aimed at far more than usual or for the
  first time, and how many addresses are new.

- **Agents say much more about what they found and did.** Each finding now says what to do about
  it, how sure the agent is (not very sure, fairly sure or sure) and how long it has been reported
  (since when, and in how many runs in a row). A run says what is new, what is still open and what
  the run before reported that this one no longer does. An agent's page draws what it found in
  each of its last runs by how serious, and a step of a run links each incident it looked at,
  says how long it took and how much it saw that was not kept. The new agents' reports read the
  same way: the daily briefing is labelled as one, and mission control shows what to do next to
  each finding.

### Fixed

- **Giving a verdict on an incident is quick again.** Saying what you think of an incident, changing
  it or taking it back used to judge every signal of every open incident again before the page
  answered, so the wait grew with everything AresGate had seen. Now only the incidents the verdict
  can make a difference to are judged again: the ones with a signal it applies to, or applied to
  before. What the incidents say is the same as before. Changing the noise filters still judges them
  all, since a filter can change any of them.

## 0.1.2

### Added

- **An incident says what was sent and to whom.** A new card draws each conversation the alerts
  are about as its two ends with an arrow between them: who it is (the name and address, where it
  is, its country, whether ntopng has it on a blacklist, what VirusTotal says of it if it was
  asked), what it went over (the transport, the kind of traffic, the service on the port), how
  much each side sent, how long it lasted and what it asked for. What every program said of the
  same flow is put together, so two programs describing one flow are one conversation, and the
  more integrations are connected, the more each conversation says.
- **ntopng's alerts are read for everything they hold**: the client and the server with their
  names, countries and blacklist flags, the ports and services, the kind of traffic, how long and
  how much, its own score and category, the technique it matched, its plain description and the
  flow's community ID. Suricata's rule metadata, a TLS flow's certificate and fingerprint, and
  what was sent where OPNsense keeps the packet are read too, and so are the addresses, ports and
  command Wazuh's logs name and what its vulnerability detector found. Each is shown with the
  alert it came from. Migration `0042` has signals read again for this.
- **The incident page says what connecting more would add.** Programs that reported are listed
  beside the ones that are not connected, with what each would add and a way to connect it.
- **The AI notes what stands out in what was sent.** It is told what the programs said of the
  traffic (through the redaction, as everything else is) and its reading lists short observations.
- **Threat intelligence can be corrected.** A false alarm or a miss no longer has to stand. Rule
  an address, a domain or a web address **safe** or **suspicious**, with a reason if you like, from
  a report, from the new "What you have ruled" card on the Threat intelligence page, or from an
  address of an incident. The ruling shows in place of what VirusTotal said, on the report, the list
  of what AresGate knows (its counts and filters follow), an incident's conversations and an
  asset's peers, with what VirusTotal said beside it. The AI is told, and the audit log records each
  ruling. It needs no connection and asks no service anything. Migration `0043` adds the rulings.

## 0.1.1

### Added

- **Settings > Agents: the agents get an AI of their own, with limits on what they spend.** An
  agent may run every hour, so how it asks the AI is now its own choice: ask whatever Settings >
  AI chose (as before), ask a provider and a model of their own (set up right there, so a
  cheaper model than the one you ask questions of can read the hourly rounds), or ask none, so
  the agents only look. Their spending has a daily and a monthly limit apart from the ones on the AI
  usage page, and reaching one stops only the agents. Migration `0040` adds the settings.
- **What an agent costs is on its page.** Every run keeps what it used of the AI: how many
  requests, tokens (how many were already cached), what it cost and which model answered. An
  agent's page has a *What it costs* section with the 30-day cost, requests, tokens, the share
  that was cached and a chart of each day, a run says what it used, each agent's card shows its
  30-day cost, and the Agents page adds up what they all cost against their limits.

- **Agents remember their last run.** Each run is told what the agent's last finished run
  reported, so it says what has changed instead of saying it all again, and every finding is
  marked *New* or *Still open*. What the last run said goes to the provider through the same
  redaction as everything else.
- **Four more things agents can look at**, which the assistant can ask for too: devices that
  appeared recently, the alerts reported most (and how widely), the ports the firewall refused
  most connections to, and open incidents that say the same thing about different subjects. The
  threat hunter and the intelligence analyst use them.
- **Each kind of agent says what it needs, and how to set it up.** The agent's page, the sheet
  that makes one and the Agents page show whether the AI, an alert source, VirusTotal or known
  devices are there, what to do when one is not and a link to where, and the steps to set the kind
  up from the start.

- **A noise cleaner agent that tidies the incident list.** It finds open incidents that say the
  same thing, quiet ones nothing has touched for three days and ones the AI is sure are noise,
  and suggests dismissing, resolving or marking each, never anything serious. Each suggestion on
  the agent's page says how sure it is and which incidents it would change, is applied with one
  press and can be taken back. Under Settings > Agents, *Tidying up* lets it do the surest of it
  itself, which the Activity page records. Migration `0041` adds the suggestions.

- **Four more agents.** A *vulnerability scanner* reads what the web, mail and SSH services of
  your devices announce (an expired or weak certificate, an SSH server that still speaks protocol
  1, a password asked for in the clear, the software and version a service announces), a *rogue
  device watch* tells you which new device to check, a *firewall reviewer* reads what the firewall
  turned away and says what to change, and a *penetration test planner* works out from what the
  other agents found how an attacker would most likely get in and what to close first, on paper
  and sending nothing. The scanner is allowed on the agent and run by hand like the exposure
  scanner. The assistant and the agents can also read what the agents last reported
  (*agent_findings*).

### Fixed

- **Two pages asking for the AI's settings at once no longer fail the first time.** The settings
  row was made by whichever request got there first, and the other stopped on a duplicate key.

## 0.1.0

### Fixed

- **Pressing Save and test again no longer takes back that a connection was tested.** Saving wiped
  how the last test went even when nothing had changed, so when a limit held the next test (as on a
  free VirusTotal key, a minute after it asked for fewer requests) the connection went back to
  "Not tested yet". Now what the last test found stays until an address, certificate, option,
  service or key is changed, which is when it stops being about what is saved.

### Added

- **The incident page shows what each program knew.** A new *What the programs saw* card adds up
  what the connected programs said beyond the basics: how many alerts each reported and what it
  added, the MITRE ATT&CK techniques Wazuh matched, the machines and applications the alerts were
  about, and the host names, URLs, users and countries they named, drawn as bars. Under *What kept
  happening*, each alert can be opened to see what each program said of it: the rule's own
  facts, its groups, the technique, how much traffic the flow carried and the log line. When
  OPNsense, ntopng and Wazuh report the same alert it is one alert with each program named as
  having seen it, counted once, and what each said is kept side by side. Alerts filed before this
  fill in as the worker reads their events. Migration `0039` adds the columns.

- **Agents.** A new Agents page makes standing instructions that look at your network for you, on a
  schedule or when you ask. Make a threat hunter, an intelligence analyst, a health watch or an
  exposure scanner, give it your own instructions, and follow each run as a graph that lights up
  step by step, with what it looked at, what the AI made of it and the findings it settled on,
  each citing the incident or integration it is based on. An agent only reads. The exposure scanner
  tests your own devices for risky open services by connecting and nothing more, and only after you
  allow it, only when you start it. Agents are built with LangGraph, with its tracing off, and
  work in light and dark and on a phone.

## 0.0.10

### Added

- **The asset page says what each peer is and which port.** Under Traffic with, each address an asset
  talked to, or that talked to it, shows the ports used at the far end (with the service a
  well-known port stands for) and what threat intelligence has kept of the address: its
  judgement, how many engines flagged it, and who owns it. An address on the home's own network
  says so, and one with nothing kept yet says it hasn't been checked. Nothing is asked of a service
  to show it.
- **AresGate builds its own record of threat intelligence.** Every answer VirusTotal gives is kept
  for good, with when the subject was first asked about, how often, and when its judgement last
  changed and from what. The Threat intelligence page lists it all under "What AresGate knows",
  newest first, to search and to narrow by judgement, and reading it asks VirusTotal nothing.
- **Check again.** A report has a Check again button, which asks VirusTotal for a newer answer
  than the one kept.

### Changed

- **Answers are kept up to date where they change soonest.** Something engines flagged, or that
  has no report yet, is asked about again after two days, and something no engine flagged after a
  week. The background lookups ask about addresses with no answer first, then renew the answer
  that went out of date longest ago.
- **A search shows the answer kept when VirusTotal can't be asked.** While a limit holds, or when
  VirusTotal doesn't answer, a search for something AresGate has an answer for shows that answer
  and says why it wasn't checked again, where before it was refused.

### Fixed

- **Reaching the free limit no longer reads as VirusTotal being broken.** When VirusTotal asks for
  fewer requests during a test, the test now passes and the connection shows as connected, where
  before it stayed "Not tested yet". When AresGate's own limits hold a test, the page says so in a
  notice, with how long to wait and that the connection is still set up, instead of in a red
  failure. The log of requests marks a request that got HTTP 429 as held back by a limit, not as
  failed.
- **Testing a local Ollama model no longer says it "didn't answer in time" while it loads.** A model
  that has to be read from disk takes a while to load, and the test gave up after ten seconds. The
  test now asks Ollama to load the model first, waits up to three minutes for it, asks Ollama to keep
  it in memory for ten minutes, and says whether the model was already loaded or how long loading
  took. If loading runs out of time, the message says so and what to try.

## 0.0.9

### Added

- **Search VirusTotal by hand.** Once VirusTotal is connected and tested, the Threat intelligence
  page takes an IP address, a domain or a web address and shows what VirusTotal reported of it:
  whether engines flagged it as malicious or suspicious, their counts, the community score, the
  categories and a link to its page there. A search shares the free key's limits, so one that would
  go over them waits, and says how long. Nothing private, and nothing on the home's own network, is
  sent.

### Changed

- **VirusTotal's free allowance lasts the day.** On a free key the background lookups are four
  minutes apart, so they use at most 360 of its 500 a day, spread over the day, and the other 140
  stay for searches by hand. Before, the free key's 15-second spacing let a backlog of addresses use
  the whole day's 500 in about two hours.
- **VirusTotal is tested by hand only.** The connection was tested every five minutes, and each
  test spent one of the free key's 500 daily lookups. Now a test runs only when you press Test.
  One made while VirusTotal's limit holds is not sent, and the connection stays as it was.
- **An internet integration is narrower.** It reaches only its own address and port, over HTTPS,
  and AresGate sends it nothing but GET requests.

- **The Threat intelligence page says what it needs.** With no threat intelligence integration
  connected, the page says it needs at least one, and its button opens the Integrations page.
  Before, it named VirusTotal only and opened VirusTotal's own page.

### Fixed

- **A search you've already made isn't sent again.** AresGate keeps VirusTotal's answer about each
  address, domain and web address in one row each, for a week. A search for a subject answered in
  that week is shown from what was kept, with no request and nothing counted, so repeated searches
  no longer use up the free key's day. This adds migration `0036`, which moves the reports of
  addresses into the new table.
- **A used-up daily limit is not a failure.** When VirusTotal's 500 daily lookups ran out, the
  connection showed as failing and AresGate kept asking. Now it stays connected, nothing is sent
  until the count resets at 00:00 UTC, and the integration page and the threat search say so. A
  search that AresGate kept the answer to is still shown while the limit holds.
- **VirusTotal connects again.** Its address is on the internet, and AresGate looked for it on your
  own network, which refused it. Its certificate is now checked by the certificates this computer
  trusts, as any public site's is, so there is no certificate step to look up for it. Its address
  stays the one VirusTotal has.

## 0.0.8

### Added

- **Verdicts can say where a device's traffic goes.** A device that calls its own cloud, such as a
  camera talking to its servers, can now be called normal for that network and nothing else it
  does. The incident page offers *Traffic from 192.168.1.20 to 52.1.2.0/24*, and the Verdicts page
  lists it. Attacks on the device, and what the service sends back, still count.
- **Each asset has a page of its own.** Its name on the Assets page opens what AresGate knows of it:
  when it was last listed and whether it is there now, the addresses it has had and which it has
  now, the programs that list it and how each one did, the interfaces it is on, the traffic ntopng
  measured for it over the last day or the last week, the events its addresses were in, what it
  talked to and what talked to it in the last week, the incidents its addresses are in, and the
  verdicts given about it. The page asks again every 30 seconds and keeps what is on screen when that
  fails. It is served by `GET /api/assets/{key}`.
- **VirusTotal tells the AI what the internet side of an incident is.** Its integration asks
  VirusTotal how many security vendors flag each internet address an incident names, and who owns
  it, and the AI reads those reports with the incident. Only addresses on the internet are sent,
  never one of your own. Its address is fixed, its key is write-only, and the access level is
  chosen on its page, with the free public API's terms said beside the choice.
- **Noise filters say how long a repeating scan may pause, and how few low alerts are too few to
  ask about.** Settings > Noise filters has two more settings. A scan or a brute force that goes
  quiet for less than the time you choose (1 to 24 hours; 4 and 6 hours until you change them) is
  still one incident, up to a day. An incident made of one program's low-severity alerts is set
  aside until it has as many as you choose (1 to 10; 1, the default, is no minimum), so a lone low
  alert is never asked about. Both appear in *What this changes* and in the activity log. A new gap
  applies to the signals that arrive after it is saved.

### Fixed

- **An interface's first ntopng alerts file as one incident.** When AresGate first reads ntopng on
  an interface, the alerts from its first half hour used to open an incident for each address they
  were about, so one start could make dozens of incidents in minutes. They now file as one incident
  for the interface, which says how many alerts it folded in. Alerts after that half hour file as
  before. An interface whose alerts AresGate had read before this keeps filing as it did.
- **The Assets page leaves out the Internet side.** The firewall's ARP table lists the devices on
  its WAN side too, such as the provider's equipment with public addresses, and they were listed
  as assets. Now a device whose addresses are public and that is not one of the firewall's own is
  left out, and the page says how many were left out. The firewall's own addresses (the ARP
  table's permanent entries) stay listed. A network of yours on the Internet interface leaves out
  what is on it, and a network of your home keeps what is on it, which takes precedence.

## 0.0.7

### Added

- **Alerts for real attacks, that say why and take themselves back.** A Discord channel can now be
  told only of **real attacks** (the incidents on the Threats page, an attack going on now) and no
  longer of every scan: a new channel starts that way, and a channel made before keeps the rules it
  had. Each message says why in the words of the incident's own page (*Why AresGate thinks so*),
  how far the attack got (*Looking around → **Trying to get in***), how sure and how serious. The
  channel hears of an attack again only when it goes a stage further (*Escalated:*), and when an
  incident it was told of turns out not to be a threat, because you called it not suspicious, you
  resolved it or the AI set it aside, the message in Discord is **changed** to a grey *Stood down:*
  note, so a warning never stays up for nothing. The **Rules** sheet is rebuilt around three cards
  (**Real attacks only**, **Everything serious**, **Custom**) and draws the message as Discord will
  show it, made by the same code that makes the real ones, for the first message and for the one
  if it escalates; **Send a sample alert** on a card sends that message to the channel, marked as
  a sample. AresGate asks Discord to name each message it sends (`wait=true`) to find it again.
  A channel on **Everything serious** or **Custom** gets the same facts and reasons (*Why AresGate
  thinks so*, how sure, how serious, how far it got), so a message about something less than a
  threat still says how much it is worth getting up for.
  This adds a migration (`0030`: `alert_destinations.mode`, and `message_id` and `target_id` on
  `alert_deliveries`). `GET /api/alerts/sample`, `POST /api/alerts/destinations/{id}/sample`.
  [Alerts](DOCS/alerts.md) has the rules and what was read from Discord's documentation.
- **Alerts are sent: a notifier with de-duplication, retries and a delivery log.** The worker now
  tells each Discord destination of the incidents its rules choose, which until now it only
  previewed. An incident is told **once**, and again only when it gets worse (a higher severity or
  band of confidence) or is reopened after you dealt with it; one you resolved, dismissed or called
  not suspicious before its message went is not sent. Quiet hours hold messages and tell what
  waited as one summary, a destination hears of at most its limit an hour and the rest in one
  summary, a failure is tried again after longer waits (and as long as Discord's `retry_after`
  says) and then given up on, and a webhook Discord refuses is never tried again until its address
  is replaced. What a message says follows the destination's detail setting, and what the network
  says is shown as plain text, so it cannot format a message or ping anyone. A new **Delivery log**
  on the Alerts page lists every message and what became of it, in words, with a filter by
  destination and state; `ARESGATE_ALERT_LOG_RETENTION_DAYS` (default 30) sets how long it is
  kept. [Alerts](DOCS/alerts.md) has the rules.
- **Threats: a few real attacks instead of seventy thousand alerts.** A new **Threats** page (in
  the menu, and on a phone in the bottom bar, where Logs moved behind **More** to make room) takes
  what programs reported down to what matters, and says how at each step: *reports*, *alerts*,
  *incidents*, and the lanes **Threat**, **Suspect** and **Background**. An alert that two programs
  report about the same traffic within two minutes (OPNsense's intrusion detection, ntopng and
  Wazuh each can) counts once, and an alert said again and again counts once for each stretch of
  time (`Event.twin_of`, `app/events/twins.py`); an incident lists what kept happening as one line
  with a count, and says how many of its alerts another program had already reported. Each alert
  is placed on a short path (looking around, trying to get in, a sign it worked), and an incident
  that went past looking around is a threat and is never set aside. Every incident's page has a
  **Where it stands** card with its lane and each fact that put it there. The dashboard's alert
  count says how many reports it came from, *Needs you* lists only threats and suspects and leads
  to Threats, and what the AI set aside is counted and linked. The Incidents page can be narrowed
  to a lane or a kind (`lane`, `family`), and changing every incident that matches a search follows
  them. [Threats](DOCS/threats.md) has the rules.
- **Kinds of incident, judged once by the AI.** Hundreds of scanners each make an incident of their
  own but are one *kind* of thing: the same program, the same words, the same sort of place. The
  new **Kinds of incident** list and a page for each kind say what the AI makes of it (noise, a
  probe, an attack, a compromise or unclear, how sure, and why) and lists a few of its incidents.
  The AI is asked about a kind, a dozen kinds to a request, and one answer covers every incident of
  it, so reading seventy thousand alerts costs a few questions. The start of every request is the
  same, so providers that cache a prompt (OpenAI, Anthropic) read it at a discount, and how many
  kinds it judges by itself follows the usage level on the AI usage page (none on *Very low*). You
  can **Ask the AI** on any kind, and your word outranks it: *Always background*, *Never set
  aside*, or take it back. `GET /api/threats/overview`, `/families` and `/families/{id}`, `PUT`
  `/families/{id}/call` and `POST /families/{id}/judge`; the code is `app/threats/` and
  `app/ai/families.py`.
- **Settings > Threat detection.** *How sure before it is a threat* (65 until you change it),
  whether the AI may set harmless incidents aside and how sure it has to be (80, never for a
  critical one), whether a threat needs the AI to agree while it is watching, what is open to the
  internet (nothing, some ports, or not sure) and a note about your network in your own words,
  which the AI is told. As with the noise filters, the page works out what saving would do to the
  lanes before you keep it. `GET` and `PUT /api/threat-settings` and `POST
  /api/threat-settings/preview`.
  This adds a migration (`0028`: `incident_families`, `threat_settings`, and columns on
  `incidents`, `incident_signals` and `events`).
- **Noise filters, in Settings.** A new **Settings > Noise filters** page decides what AresGate asks
  you about without a verdict from you. *How sure before it asks you* is the confidence an
  incident has to reach (1 to 100, 35 until you change it) for the dashboard's sentence, the Needs
  you lane and the filtered-out counts, with what the number means in words. *What each program has
  to be worth* sets, for each program that reported an alert in the last week (with what it
  reported by severity beside it), the lowest severity that counts: everything it reports, medium
  and up, high and up or critical only. *Inside your network* sets aside alerts whose source and
  destination are both private addresses (10.x, 172.16 to 172.31, 192.168.x, 100.64.x, link-local
  and unique local ones). A signal set aside is kept, listed in the incident's timeline with a chip
  that says which filter did it (*Set aside: under this program's severity*, *Set aside: inside
  your network*), counted in its signals, and adds nothing to how serious or how sure the
  incident is, as with a verdict; an incident made only of such signals is sure of nothing and says
  why. Your verdicts come first (a signal one is about is judged by it, even a real threat), and a
  program's ban is never set aside. The page works out what saving would do as you change it (the
  incidents that need you, those filtered out and the alerts set aside, now and with the
  settings as they are on the page) by judging the incidents that are going on as the settings
  would and putting them back, so the figures are what saving does. Saving judges them again at
  once; incidents that are over keep what was said at the time. Each change is in Settings >
  Activity. The API is `GET` and `PUT /api/noise-filters` and `POST /api/noise-filters/preview`;
  the rules are in `app/incidents/filters.py`, and the dashboard asks for the saved floor.
  This adds a migration (`0027`, `noise_settings`, `incident_signals.filtered_by` and
  `incidents.filtered_count`).

## 0.0.6

### Added

- **`make stop` and `make start`.** `make stop` stops AresGate and keeps its container, so the data
  volume stays in use; `make start` starts the same container again, with every setting as it was.
  `make down` (which removes the container, and keeps the data volume) says so when it finishes,
  and warns that Docker's clean-up tools can delete a volume no container uses.
- **`make data`** shows the Docker volume that holds your settings and data, when it was made and
  which container uses it, for finding out whether AresGate is on the volume you used before.
- **The container's log says whether it found its data.** The start now logs `using the database
  already in the data volume (made <date>)` or `making a new database: the data volume has none`,
  the second being the sign that this is not the volume that held your settings.
- **A test that stops and starts every way.** CI saves an integration and an AI provider, each with
  a secret, then does `make stop` and `make start`, `make restart`, and `make down` and `up`, and
  after each checks that the account signs in, the settings are in the API, the sealed secrets
  in the database are the same bytes and the app secret key is the same file. Before, only a
  restart was tested for the account, and `down` and `up` only for health.
  See [DOCS/operations.md](DOCS/operations.md#stopping-and-starting).
- **What is making the noise, on the dashboard.** A card under the charts says which program
  reported most of the alerts (and how many of those were high or critical, and how many were
  between two addresses on your own network), then lists the alerts that were reported most often:
  how many times and what share of all of them, how serious the worst was, from how many addresses
  to how many, and over what time. **Quiet this** gives a low priority verdict for that alert from
  that program (the same verdict the incident cards give, so it has a note, an *Undo* for ten
  seconds and a place in Settings > Verdicts to take it back), and **See in logs** opens the Logs
  page on that alert in the same window. An alert that names no rule can be looked at but not
  quieted, since there is nothing to judge it by. The numbers come from `noise` in
  `GET /api/dashboard`, worked out by `alerts_by_source` and `noisy_signatures` in
  `app/dashboard.py`, so the analyst's tools can ask the same question.
- **The dashboard's sentence and the Needs you lane go by what needs you.** *Needs your attention*
  used to count every high or critical alert, so a network full of chatty rules said "3,642
  serious alerts" while nothing was wrong. It now counts incidents: those still open or being
  investigated, not called quiet by your verdicts, and at least as sure as the floor (35, medium
  confidence). *Needs your attention* is for the ones AresGate is highly confident of (65 and up),
  *Worth a look* for the others that need you, and *All quiet* says how many alerts there were and
  that none of them needs you. A line under it counts the incidents (how many, how many need you,
  how many were filtered out), with a link for each reason (not sure enough, called not suspicious
  or low priority, already handled) to the Incidents page on exactly those. The Needs you lane
  lists the same incidents the sentence counted, and *See all* opens the Incidents page on them.
  The Alerts tile is colored by what needs you and not by the worst alert. The numbers are
  `attention` in `GET /api/dashboard`, worked out by `attention` in `app/dashboard.py`. What
  decides whether one incident needs you lives in one place, `app/incidents/attention.py`
  (`standing`, with the same rule as SQL in `clauses`), for the dashboard, the lane and anything
  that later has to choose what is worth a message.
- **Look up the certificate a system presents and trust it, whatever it is.** Under
  **Certificate** on every integration's page, **Look up the certificate** is now offered whichever
  way of checking is chosen, not only after choosing the third one. It shows what the system
  presented (its own certificate, who made it, who it names, how long it is good for, its SHA-256
  fingerprint to compare with the system's own, and the others it sent with it), says in words
  whether the way chosen would already accept it and, if not, why, and **Trust this certificate**
  pins it, a self-signed or expired one included. A test that fails over a certificate now has
  **Review the certificate** where the failure is said (on the card and in the report), and
  **Trust and test** trusts it, saves and tests again in one step, so connecting Wazuh (two
  connections) or any system with its own certificate no longer means finding a fingerprint first.
  The three ways of checking are as they were. If a pinned system presents a different certificate
  later, the test now says "The certificate has changed" with both fingerprints, and the same
  button reviews and trusts the new one
  ([DOCS/integrations.md](DOCS/integrations.md#trusting-the-certificate-a-system-presents)).

### Changed

- **AI usage is a place in the menu of its own.** It was a page of Settings. **AI usage** is now
  in the menu, after Interfaces (behind **More** on a phone), with the range and **Refresh** beside
  its title, and the command palette finds it by name or by *spending*, *tokens* or *budget*. The
  spending limits and the usage level slider are on it as before. Which AI provider and model to
  use is still chosen in **Settings > AI**. The old `/settings/ai-usage` address leads to the new
  page, so a bookmark keeps working. The message that says a spending limit is used up now points
  to the AI usage page.

### Fixed

- **A certificate authority made by OpenSSL can be pasted**: under **Certificate**, **A certificate
  authority I paste** refused every authority whose certificate has no key usage extension, with
  "CA cert does not include key usage extension". That is how OpenSSL's own `req -x509` makes an
  authority, and how Wazuh's certificate tool makes `root-ca.pem`, so the cure the test gave for
  the Wazuh indexer ("paste the authority") could not work. Python 3.13 turned on its strict
  RFC 5280 checks for every connection; they stay on for the certificates the computer trusts and
  are off for an authority you pasted yourself. The signatures, the dates and the name are still
  checked.
- **The test says whose certificate it is, and Wazuh's page says why Let's Encrypt isn't it**:
  Wazuh's instructions for Let's Encrypt are for the dashboard only. The manager's API (port
  55000) and the indexer (port 9200) answer with the certificates Wazuh made for them, so choosing
  **The certificates this computer trusts** failed on both however valid the dashboard's
  certificate is. A system that sends only its own certificate, issued by an authority that gives
  no address to fetch it from, is now called what it looks like (an authority of the system's own,
  named, rather than a public one missing from the chain) and a certificate with no names says to
  pin it. The Wazuh connections show a note beside **Certificate** saying which certificate answers
  there and what to choose, and the setup instructions say how to compare the API's fingerprint.
  ([DOCS/integrations.md](DOCS/integrations.md#wazuh)).
- **An Alerts page, and Discord channels to send alerts to.** **Alerts** is a new place in the
  menu. Add the webhook of a channel on your own Discord server, give it a name, and choose
  **Send test message** to check it reaches the channel; each destination shows whether it works
  and, if not, why in words (Discord doesn't accept the webhook, is limiting how fast messages
  go, or didn't answer). A destination can be turned off, renamed, given a new address or
  removed. The webhook's address is a secret, since anyone who has it can post to the channel:
  it is sealed like the other credentials, shown only as the end of its number, never returned by
  the API, kept out of the API log and the audit log, and checked when it is typed and again
  every time it is used. Only `discord.com` and `discordapp.com` webhook addresses are accepted,
  and the request goes through the same network guard as AI providers (the internet only, no
  redirects, the certificate verified). Messages are sent so that nothing in them can ping
  `@everyone`, a role or a person. This is the first slice: the sender with its delivery log and
  a daily digest come next. See [DOCS/alerts.md](DOCS/alerts.md), which also says what was read
  from Discord's documentation and what was inferred.
- **Rules for what each alert destination is told about.** Each destination has a **Rules** sheet
  (a side sheet, the whole screen on a phone). A new destination hears only of what is medium or
  worse and what AresGate is at least 65% sure of. The rules can raise or lower both, limit it to
  incidents certain programs saw or kinds of activity (scanning, brute force), set quiet hours (a
  start, an end, a time zone, and whether critical threats still get through; what came in is
  held until they end, not dropped), cap messages an hour (the rest are said in one summary), ask
  for a new message when an incident gets worse, and choose how much a message says (brief,
  standard or full; only full names devices on your network). An incident you called not
  suspicious or low priority, or resolved or dismissed, is never sent, whatever the rules say; one
  you called a real threat skips the severity and confidence floors. While you change the rules,
  the sheet shows what they would have done with the last 24 hours: how many messages, what was
  left out and why, and the newest few that would have been sent. Nothing is sent yet: the sender
  that uses these rules is the next slice.
- **An Assets page: every device the connected programs can see, as one list.** It is in the menu
  after Logs (behind More on a phone). OPNsense lists the devices of its ARP table and DHCP
  leases, ntopng the hosts it knows the hardware address of, and Wazuh its agents; what they say
  about one device is put together when the page asks, so a device two of them list is shown
  once, and it says which programs listed it and how ("OPNsense: ARP table, DHCP leases"). A
  Wazuh agent has no hardware address, so it is matched to the device that had its address, else
  to the one device whose name is the same, and the card says which; one nothing matches is an
  asset of its own. Each asset says whether it is **online** (listed in the last ten minutes by
  something that can only list what is there now: the ARP table, an ntopng host or an agent that
  is in touch), **seen recently** (listed in the last day, as a DHCP lease alone is, since a lease
  outlasts the device) or **not seen for a while**; whether it is **new** (first listed in the
  last week, not counting the devices found on the first day, which are the network as it was);
  whether its hardware address is a **private** one the device made up; and whether anything says
  what it is. Search finds words in the name, maker, addresses (a hardware address with colons,
  hyphens or neither) and the programs that list it; you can narrow the list by state, by
  program, by interface (by the networks of Interfaces), to what is new and to what is not
  identified, and order it by when it was listed, name, address or when it was first listed. What
  is chosen is in the address of the page, so a link or the back button brings it back. With no
  program connected that can list devices, the page says so and leads to Integrations; with one
  connected that has not listed any, it leads to Status. See [DOCS/ui.md](DOCS/ui.md#assets).
- **Which program listed a device is now stored.** `device_sources` keeps, for every device, each
  program and way that has listed it with the first and last time, and `host_listings` keeps the
  machines a program lists without a hardware address (Wazuh's agents). Collectors say how they
  list with `context.record_devices(sightings, via)` and `context.record_hosts(hosts, via)`; see
  [DOCS/development.md](DOCS/development.md#storing-devices-from-a-collector).

## 0.0.5

### Added

- **Setup instructions for every integration, in a window.** Each integration's page has a
  **Setup instructions** button (the main thing to do until it is connected, instead of a panel
  that took the top of the page; the **Documentation** link stays beside it). The window gives
  numbered steps, each with a short title, the menus to go through (OPNsense: System, Access,
  Users; ntopng: Manage Users; Wazuh: Server management, Security, and Indexer management,
  Security; CrowdSec: `cscli bouncers add`), the exact values to pick or enter (names, roles and
  privileges as the product spells them) and which AresGate field what the step produced goes
  into. A step says what is easy to get wrong, and what was worked out rather than read from the
  documentation, so a guess isn't passed off as documentation; the pages each guide was written
  from are listed at the end. It takes the whole screen on a phone, and works with the keyboard
  (focus moves in, Escape closes it, focus goes back to the button). The old ntopng text told you
  to edit "the user AresGate will use" without saying where to make one or where the token is.
  See [DOCS/integrations.md](DOCS/integrations.md#setup-instructions).
- **One place that asks the AI, and what it is shown.** Everything AresGate will ask a model
  (incident triage and the chat come next) goes through `backend/app/ai/gateway.py`, which is the
  only code besides the connection test that calls a provider. Before a hosted provider reads
  anything, what identifies your home is replaced by stand-ins only AresGate can turn back
  (`HOST_12` for a device, `WAN_n`, `EXT_n`, `MAC_n`, `NAME_n`, `USER_n`); passwords, keys and
  tokens are taken out at every level; log text goes between `<data>` tags that the instructions
  say are evidence, never orders; and the whole prompt is gone over once more. **Settings > AI >
  What the provider sees** chooses the level: *Strict* (everything, even attackers' addresses),
  *Balanced* (the default: your devices and names, not attackers on the internet) or *Local*
  (nothing, only for a provider on your own network), each shown with the same event as a
  provider would read it. See [DOCS/operations.md](DOCS/operations.md#ai-providers).
- **A record of every request to an AI provider.** The new `ai_calls` table keeps when, what for,
  the provider and model, the level, the prompt and the answer exactly as the provider saw them,
  the tokens (cached, written and thinking counted separately), the cost from the catalog's
  prices, how long it took and why a request failed. It keeps 90 days
  (`ARESGATE_AI_LOG_RETENTION_DAYS`). The usage page reads it.
- **The AI reads incidents.** The incident page has a new card, *What the AI makes of it*: what
  kind of thing the AI thinks it is (a possible compromise, an active attack, a probe, harmless or
  unclear), how sure it is, the story in plain words, what to check, and the verdict it would give
  with one button to give it. It is shown as the AI's opinion, with who read it and when, and
  changes nothing by itself. Pressing *Start investigating* now has the AI read the incident, and
  says plainly when AI is off or no provider is chosen. The worker also reads new incidents as
  they come in, as much as the usage level allows (*Medium* for now: medium and serious ones, at
  most 20 an hour), and the incident list shows the AI's word beside the others. Nothing is asked
  when AI is off, and everything the AI is asked is recorded. See
  [DOCS/operations.md](DOCS/operations.md#ai-providers).
- **How much AI is used without being asked.** **Settings > AI usage** has a slider from *Very low*
  to *Maximum* that sets what the worker reads by itself: which incidents, how many an hour and
  when it reads one again, in words made from what the worker really does. *Very low* reads
  nothing by itself. It only decides what is done without being asked: asking the AI about an
  incident, and your questions to the assistant, are answered at every level. Changing it is in the
  activity log.
- **What AI took and cost, and spending limits.** The new **Settings > AI usage** page adds up
  every request to an AI provider: the cost, tokens and requests for the last 7, 30 or 90 days
  against the stretch before, the month so far and where it is heading, the days as stacked bars by
  use (in cost, tokens or calls), the same by provider, model or use, what took the most (an
  incident links to its page), and every request, each opening to show exactly what the provider
  was sent and what it answered, with the stand-ins it was given. The costs are estimates from a
  price list that the page links to and dates, and requests to a model with no known price are
  counted in tokens and say so. *Download as a spreadsheet* saves the range's requests as a CSV.
  You can also set **spending limits** for the last 24 hours and for the month: past 80% the meter
  warns, and when one is used up AresGate stops asking providers that charge by the token, the
  worker included, and says which limit it was. A provider on your own computer is never stopped.
- **An assistant you can ask about your network.** The new **Assistant** page in the menu answers
  questions in plain words ("What needs my attention right now?", "Are all my integrations
  working?"). It never answers from memory: it is shown an overview of the network and either
  answers or asks to look something up, from a short list of reads (open incidents, one incident,
  recent alerts, who the firewall blocked most, a device, how the integrations are doing), and
  then says what it looked at and what it is based on, with links to the incidents and
  integrations. It can only read: nothing it can do changes AresGate or the network. Everything it
  is shown goes through the same privacy level as the rest, every request is recorded under
  Settings > AI usage, and every answer has a button to read exactly what the provider was sent.
  Conversations are kept until you delete them. An incident's AI card has *Ask the assistant*,
  which opens the chat with a question about it ready to send.
- **Interfaces, the foundation**: the parts of the network can now be named, with a role
  (Internet, DMZ, Home, Guest, IoT, VPN, Management or Other) and their networks, and the ports
  the programs report data under (OPNsense `igc0`, ntopng `eno1`) can be placed on them, so that
  what different programs say can be read as one. Finding the ports is on request
  (`POST /api/interfaces/discover`) and looks at the events of the last three days, the metrics,
  the connections that are one feed (CrowdSec, Wazuh) and the interfaces ntopng lists. Suggestions
  from the names (`wan`, `guest`, `wg0`) are shown and never applied by themselves. Events now
  keep the port they came in on (OPNsense's firewall log and Suricata alerts say it), and the
  interface is worked out when data is read, so placing a port somewhere else relabels what was
  stored before. Changes are in the audit log. The page for all this comes next
  ([DOCS/development.md](DOCS/development.md#interfaces-the-parts-of-the-network)).

- **The Interfaces page**: a new place in the menu for the parts of your network. It says how
  many feeds are left to decide, offers AresGate's guesses (a port called `wan` is the Internet,
  `guest` is Guests) to confirm, change or ignore, shows a card for each interface with its traffic
  of the last day, its alerts and its devices, and lists the feeds that are not placed yet with a
  control to place each one. Each interface has a page with its traffic chart, its numbers and its
  data sources; moving a feed says what moved and offers **Undo**. The sheet that names an
  interface and chooses its role from cards fills the screen above the bottom bar on a phone.
  Alerts are counted on the interface their port was placed on (`GET /api/interfaces/overview`)
  ([DOCS/development.md](DOCS/development.md#interfaces-the-parts-of-the-network)).
- **ntopng can be read on several interfaces**: the **Interface** list is now **Interfaces**, and
  one or more can be chosen (up to 16). The interface traffic, hosts and alerts collectors read
  each in turn, the connection test says what each has seen, and an alert keeps the interface it
  came in on, so that it can be placed on a part of the network. A connection saved with one
  interface keeps reading it, and a new one starts on every interface that has seen traffic
  ([DOCS/integrations.md](DOCS/integrations.md#ntopng)).

### Fixed

- **Why a certificate isn't trusted is explained**: a valid Let's Encrypt certificate was reported
  as "unable to get local issuer certificate", which is what OpenSSL says both when a system sends
  only its own certificate, without the intermediate authority's (`cert.pem` instead of
  `fullchain.pem`, which browsers forgive), and when an authority is simply unknown. AresGate now looks at what the
  system sends and says which, names the authority and the cure: serve the whole chain, or paste
  that authority's certificate, or pin the fingerprint. Expired, not yet valid, self-signed and
  made-for-other-names certificates are named in words too. The image's smoke test fails if the
  image has no certificate authorities
  ([DOCS/integrations.md](DOCS/integrations.md#when-a-certificate-that-looks-valid-isnt-trusted)).

- **ntopng's interface is chosen by name**: the **Interface ID** box is now an **Interface** list.
  **Fetch interfaces** asks ntopng (before anything is saved, with what is typed) and names each
  interface with its ID, where its traffic comes from and what it has seen; a saved connection
  fills the list in when the page opens. ntopng answers an interface it doesn't have with HTTP
  400, which every ntopng collector used to report as "ntopng answered HTTP 400": it now says
  that ntopng has no interface with that ID and which ones it has. The connection test and the
  *Interface traffic* collector say plainly when the interface has seen no traffic yet, so
  "nothing comes in" has a reason on the page
  ([DOCS/integrations.md](DOCS/integrations.md#ntopng)).

## 0.0.4

### Added

- **The CrowdSec plugin on OPNsense is read**: if the plugin is installed, AresGate reads its bans
  and its alerts every minute through the OPNsense connection that exists, with no second key. A
  ban is the same event as the one the standalone CrowdSec integration stores, so an attacker
  read both ways is one, and the number banned now is kept as a metric. An alert is dated by its
  own time and says the scenario, the address and where it is. The user needs OPNsense's
  **CrowdSec** privilege, which also allows changing the plugin, and what the Collection card
  shows without it is in [DOCS/integrations.md](DOCS/integrations.md#crowdsec-on-opnsense).
- **Incidents flagged on the traffic chart**: the dashboard's traffic chart has a flag above it
  for each incident that began in the day or week and was medium or worse, with a dashed line down
  to the time, so a spike can be read against what was going on. A flag links to its incident
  and says what it is when you point at it or tab to it; flags too close to tell apart become one
  with a count, and the chart's table view has a column for them. `GET /api/dashboard` now also
  answers `marks`: the incidents of the window, up to twelve, that are worth a flag.
- **What was done about an incident**: every card in the incident list now has a chip that says
  *Banned*, *Partly banned*, *Ban ended*, *Blocked* or *No response yet* (an incident about a
  rule, with no address to act on, has none), and the incident's page has a *What was done about
  it* section: a sentence ("CrowdSec banned 182.161.66.3. The ban has 3h 12m left."), each ban
  with the scenario that made it, where it came from and when it runs out, how often the
  firewall turned the address away (and how often after the ban) and how many alerts Suricata
  stopped, the steps in order (first seen, banned, still trying, ban ends) and what AresGate
  cannot tell, such as a program that is not connected. It is read from the events already
  stored, so nothing asks a program anything. `GET /api/incidents` and `GET /api/incidents/{id}`
  carry it as `response` ([DOCS/operations.md](DOCS/operations.md#what-was-done-about-an-incident)).
- **Saved searches**: the button beside the search box on the incidents and the logs pages now
  lists the searches you saved. Type a name under *Saved searches* and press *Save* to keep what
  is in the box (it says *Replace* when the name is taken); press one to use it, or the bin to
  forget it. Each page keeps its own, up to 50. `GET`, `POST` and `DELETE /api/searches`
  ([DOCS/operations.md](DOCS/operations.md#saved-searches)).
- **A Logs page**: every event the collectors stored, with the record each integration sent next
  to what AresGate made of it. On a computer, a table with a sticky heading, a heading for each
  day, columns you choose (and whether the time is exact or *how long ago*) and the arrow keys
  to move through it; on a phone, a card for each event. *Live* follows along every 5 seconds,
  holding new events behind a button while you are scrolled down. The same search as the
  incidents (`severity>=high source:opnsense -port:22 since:1h "failed password"`, plus `from:`,
  `to:`, `kind:`, `protocol:`, `incident:yes` and `raw:` for the integration's own record), with
  buttons that count the severities, integrations and kinds, and a chart of events over time
  where a tap on a bar narrows the search to that time. Open an event for a sheet with every
  field (each with *copy* and *show events with this*), the incident it was filed into, links
  to all events with each address, and the pretty-printed record; `j` and `k` step through the
  events. *Export* saves what a search finds as CSV or JSON (the newest 50,000, one entry in the
  activity log). `GET /api/logs`, `GET /api/logs/{cursor}` and `GET /api/logs/export`
  ([DOCS/operations.md](DOCS/operations.md#the-logs-page)).
- **A *More* button on a phone**: the bottom bar holds four places and the rest, Status and
  Settings, are behind *More*, which is marked while one of them is open.
- **Change many incidents at once**: every card in the incident list has a box, a row above the
  list picks the page (shift picks a range, Escape lets go), and once some are picked the row
  holds *Status* and the three verdicts. A status change to a few is made at once with *Undo* for
  15 seconds; a larger one, one to *all 143 that match* the search and filters, and any verdict
  are first looked over: the dialog says how many incidents and signals it touches and how many
  it would change, that a verdict holds for everything about an address (so incidents you did not
  pick can change), and lets you say why. `POST /api/incidents/bulk` takes `ids` (up to 1000) or
  `matching` (the list's own filters) and a `status` or a `verdict`, with `preview`; it is all or
  nothing, has one entry in the activity log, and answers with how to take it back
  (`POST /api/incidents/bulk/undo`)
  ([DOCS/operations.md](DOCS/operations.md#incidents)).
- **Search for incidents**: a box above the list takes words and a few terms, such as
  `severity>=high source:wazuh -port:22 since:6h ssh`: text in the title or subject, an address or
  a range (`address:203.0.113.0/24`), the program that reported it, severity and confidence
  (with `>=` and the like), status, your verdict, scanning or brute force, a signature, a
  destination port, a device on your network, whether it was banned, and when it was going on,
  with a minus to turn any term around and a comma for choices. The box shows how it understood
  what you typed as chips that each come off with a tap, says why when it can't (and which
  field you probably meant), and keeps what was listed meanwhile, with a note. Under the
  filters, buttons count the severities and programs among what was found and add themselves to
  the search with a tap. `/` goes to the box, a help button lists the ways to search and the last eight searches,
  and the search is in the address of the page, so it can be sent as a link. `GET /api/incidents`
  takes `q` and `tz` (the time zone, for `today`) and answers with `terms` and `facets`; a search
  is limited in length and terms, and the database stops one after 5 seconds. The address field
  it replaces still works from older links. Saved searches are to come
  ([DOCS/operations.md](DOCS/operations.md#the-incidents-pages)).
  it replaces still works from older links. Saved searches and the same search for the logs are
  to come ([DOCS/operations.md](DOCS/operations.md#the-incidents-pages)).
- **A phone pass over the app**: on a phone the incidents that need a decision are a row to swipe
  through, the next one showing at the edge, where three tall cards used to push the charts a
  screen down; every button is at least 44 px tall on a touch screen, the small ones next to a
  chart's title and the icon buttons included; the incident list's choices fade where they go
  past the edge of the screen; and Settings has a shorter introduction.
- **A command palette**: Ctrl or ⌘ and K, or the *Search* button in the app bar, searches for a page
  or an action from anywhere: every page in the menu and in Settings, each group of incidents,
  the light, dark and system themes, and, for a whole IP address, the incidents about it. It is
  driven from the keyboard (Enter takes the first result, the arrow keys walk the list, Escape
  closes it) and announces how many it found. New pages that join the menu or Settings appear in
  it by themselves.
- **A hero on an incident's page**: under its title, a ring drawn to how sure AresGate is (with the
  figure in it), a sentence that says what happened from what the incident holds (*3 programs
  agree*; who reported how many signals about which address over how long, whether it was banned,
  which devices on your network are involved and how often the firewall turned the address away),
  and its four numbers inside the same surface. It is the color of how serious the incident is
  until it is resolved or dismissed, and a serious one that is not over breathes faster so it
  is not missed (and stops moving for anyone who asks their system for less motion).
- **A bot that keeps coming back is one incident**: a port scan or a brute force from one
  address, or from the neighbouring addresses of its block (a /24 or /64) doing the same thing, is
  one incident however many waves it takes, instead of one for each. An incident never runs more
  than a day, so the same bot another day is another, and a scan that went quiet for four hours
  (six for a brute force) is over. Each incident says what it was doing, how many waves it came
  in, how many ports it touched and why its signals are one incident, on its card and in a new
  section of its page; incidents filed before are merged when a new signal touches them if they
  have the same status ([DOCS/operations.md](DOCS/operations.md#incidents)). The incidents API
  gains `activities`, `waves`, `port_count`, `ports_capped` and `neighbours`, and `grouping` and
  `ports` on one incident.
- **A Needs you lane on the dashboard**: under the status hero, the three open incidents that most
  need a decision, the most serious and surest first, each with *Not suspicious*, *Low priority*
  and *Real threat* right on its card. A verdict from the lane says what AresGate remembered, with
  *Undo*, and the lane asks again, so the incident you judged leaves it. When nothing needs a
  decision there is no lane. `GET /api/incidents` takes `order=priority` for the most serious
  first (the default is still the most recent).
- **A status hero on the dashboard**: the first thing on the dashboard is now one sentence in the
  biggest type on the page (*Needs your attention*, *Keep an eye on it*, *All clear*, *Set up*)
  with a ring and a glow in the color of the answer, and the four numbers that back it up inside
  it, where there used to be a flat banner above a row of tiles. Cards have a faint sheen in dark
  mode, the page a soft ambient light, the active navigation item a glow, headline numbers use
  tabular figures, and Inter is loaded with its optical-size axis. The ring, glow and sweep stop
  for anyone who asks their system for less motion. [DOCS/design.md](DOCS/design.md) says what the
  look is for and where the ideas come from.
- **Verdicts from the list of incidents**: each card has *Not suspicious*, *Low priority* and
  *Real threat* under its details, so you can judge an incident without opening it or going to
  Settings. A verdict from a card is about what the incident is about (its address, or the first
  alert where it names no address); the page says what it remembered, with *Undo* for ten seconds
  (a verdict that changed another goes back to what it was), and an incident that nothing else
  needs leaves the list. `POST /api/verdicts` now also says what a verdict replaced (`replaced`).
- **AI providers**: **Settings > AI** sets up Anthropic, OpenAI, Ollama on your own computer and
  Ollama Cloud, tests each with a single token, and turns AI on for one of them. Anthropic starts
  on Claude Haiku 5.5 and OpenAI on GPT-6 Luna, and the other models they offer (Sonnet 5.5, Opus
  5.5 and Fable 5.1; GPT-5.4 nano and mini, GPT-6.1 Terra and Sol, GPT-6 Astra) are listed with
  their prices, including long prompts, cached input and writing to the cache, read from the
  providers' pages. Instructions are marked for the providers to cache, the GPT-6 models are asked
  to think a little and given room for it, and cached and written tokens are counted separately.
  You choose one of the four as a card and see only its settings. Ollama has *Fetch models*, which
  fills the model list, and *Test connection*, and so has Ollama Cloud once it has a key; Ollama
  Cloud also asks whether the account is free or paid, because free accounts can use only some
  models and Ollama answers 402 Payment Required for the rest, which AresGate now explains. An
  Ollama on the same computer can be reached at `localhost` outside Docker, and in Docker at
  `host.docker.internal`, which the message says. API keys are sealed in the credential store and never
  shown again, hosted providers are reached only at their own addresses, and AI is off until you
  turn it on ([DOCS/operations.md](DOCS/operations.md#ai-providers)). It is `GET /api/ai`,
  `PUT` and `DELETE /api/ai/providers/{key}`, `POST` `.../test` and `.../models`, and
  `PUT /api/ai/use`.
- **Verdicts**: say that an address, a program, a signature or a mix of them is *not
  suspicious*, *low priority* or *a real threat*, and AresGate remembers it as a rule and holds
  you to it from then on. Signals that match a verdict of not suspicious or low priority are still
  listed and counted, but add nothing to how serious an incident is or how sure AresGate is, so an
  incident of nothing else never raises an alarm; one you call a real threat is certain. A rule
  that names more beats one that names less, a verdict on an address does not excuse attacks on it,
  and giving, changing or taking back a verdict is applied at once to the incidents that are not
  over and is in the activity log ([DOCS/operations.md](DOCS/operations.md#verdicts)). It is
  `GET`, `POST`, `PATCH` and `DELETE /api/verdicts`, and incidents can be narrowed by `verdict`.
- **Verdict controls**: an incident's page has *Your verdict* to say whether its address or one of
  its alerts is not suspicious, low priority or a real threat, to see which verdicts apply and to
  take one back; its signals say which of them don't count. The incident list leaves out what you
  quieted, with a switch to show it and how many there are. **Settings > Verdicts** lists every
  verdict to review, change or take back.
- **Incidents**: the alerts and bans that belong together, whichever integration reported them,
  filed by the worker every 30 seconds. Suricata's alert, Wazuh's log line and CrowdSec's ban of
  one address are one incident, with its severity, how sure AresGate is and a list of the reasons
  that add up to it (the most serious signal, other programs that agree, how often it happened,
  a ban, how many addresses it reached), a timeline of the signals, the devices on your network
  involved and how often the firewall turned the address away. You can mark one open,
  investigating, resolved or dismissed. Nothing here needs an AI provider
  ([DOCS/operations.md](DOCS/operations.md#incidents)). It is `GET /api/incidents`,
  `GET /api/incidents/{id}` and `PATCH /api/incidents/{id}`.
- **Incidents pages**: Incidents in the menu lists them (active ones to start with; narrow by
  status, severity, confidence or an address, 25 at a time, kept in the link), and each has a page
  with its status and the changes you can make, why AresGate is as sure as it is, the addresses
  and devices on your network involved, a chart of signals over time by program and the timeline
  of every signal. Both ask again every 30 seconds and work on a phone, in light and dark
  ([DOCS/operations.md](DOCS/operations.md#the-incidents-pages)). Whole-number axes on count
  charts: a chart of how many alerts there were no longer has ticks at 0.5.
- A **Dashboard** in place of the Overview page: a sentence at the top on whether anything needs
  you (it never says all is quiet while collectors are failing), the numbers for alerts, refused
  connections, new devices and collection, a chart of each OPNsense interface's traffic, alerts
  by severity, the addresses refused most and the latest alerts, for the last 24 hours or 7 days
  against the time before. It asks again every 30 seconds while it is open, keeps what it shows
  if a refresh fails, and works on a phone ([DOCS/operations.md](DOCS/operations.md#the-dashboard)).
- What the dashboard will show, as `GET /api/dashboard` for someone signed in: the alerts and the
  connections the firewall refused over the last 24 hours or 7 days, each against the stretch of
  time before it and by hour (or six hours), the most serious alert, the addresses refused most,
  the latest alerts, the speed of each firewall interface worked out from its byte counters (a
  restart that sets a counter back to zero is a gap, not a negative speed) and the devices first
  seen in that time. Each is a function of its own that the pages that go deeper and the AI
  analyst can use too.
- Charts for the pages to come: bars (ranked or by hour, side by side or stacked), lines over time,
  a heatmap of hours and days and small trend lines. Each has a legend that turns a series off,
  a switch to the same numbers as a table, readouts by pointer, touch or the arrow keys, colors
  checked for color blindness in both themes, and a layout that works on a phone
  ([DOCS/ui.md](DOCS/ui.md#charts)). The Data page uses the first: a bar chart of how much each
  integration has stored. The stat tile can now show how a number has changed and how it has
  been going.
- OPNsense's health, traffic and gateways, read every minute and kept as metrics: the load,
  uptime, memory and disk space, the processors' use, the bytes, packets and errors of each
  interface, and whether each gateway is up and how its link is doing. They are four jobs on the
  Collection card, each needing its own privilege in OPNsense
  ([DOCS/integrations.md](DOCS/integrations.md#health-traffic-and-gateways)).
- The devices on the network, listed from OPNsense's ARP table every minute and from the DHCP
  leases of Dnsmasq and Kea every five, and kept with their hardware and IP addresses, host
  names and the makers of their network cards, and when each was first and last seen. They are
  what the monitoring pages and the AI analyst will use to say which device is which
  ([DOCS/integrations.md](DOCS/integrations.md#devices)).
- A **Data** page in Settings, showing for each integration how many events and measurements are
  stored and how long they are kept, and letting you change that. It asks first when a shorter
  time would remove what is already stored ([DOCS/operations.md](DOCS/operations.md#stored-events)).
- The addresses CrowdSec has banned, read from its local API every minute and kept as events
  (the address, the scenario and for how long), with how many bans are in force as a metric. Only
  the bans that came from your own logs, by hand or from an import are read, not the community blocklist
  ([DOCS/integrations.md](DOCS/integrations.md#bans)).
- Wazuh's alerts, read from the indexer every minute and kept as events with the rule, the level
  Wazuh rates it at, the host it is about and the address it came from. The state of its agents is
  read from the manager's API too: how many are in each state as a metric, and an event for each
  one that stopped reporting ([DOCS/integrations.md](DOCS/integrations.md#alerts)).
- ntopng's hosts and traffic: how much each host on the local network has sent and received, its
  flows and its score as metrics, the hosts that are devices added to the devices, the traffic
  through its interface as metrics, and its flow and host alerts as events
  ([DOCS/integrations.md](DOCS/integrations.md#hosts-and-the-devices-among-them)).

### Fixed

- Two collectors storing events at the moment a new week begins could wait for each other and one
  of them fail that run: a collector that stores events it has not seen before (the CrowdSec
  bans) read what was stored before taking the lock that making the week takes, which makes the
  week wait for every reader to finish. It takes the lock first now.
- Creating the account with the setup code failed with "The request didn't come from AresGate"
  when AresGate was opened at `https://localhost` and `ARESGATE_SERVER_NAME` was a name of your
  own, because only the server name was accepted. `https://localhost` now works whatever the
  server name is, on the HTTPS port in use. Plain HTTP goes on to the address it was opened at
  (`localhost` or the server name), the setup code's box in the log names both addresses, and a
  change that is refused now says which addresses to use.
- A message under a field that is long enough to wrap, such as the one asking for a username on
  the setup page, ran under the label of the field below it. Every field now keeps room for the
  label, so nothing overlaps.

## 0.0.3

### Added

- Storage for the numbers the integrations measure over time, such as a firewall's load or an
  interface's traffic, for the collectors that read them to save and the charts to draw. Each is
  kept for 30 days unless `ARESGATE_METRIC_RETENTION_DAYS` says otherwise, or an integration is
  given a period of its own, as for events ([DOCS/operations.md](DOCS/operations.md)).

### Fixed

- Every build of the image now gets the newest fix of every package, as
  [DOCS/security.md](DOCS/security.md) says. The Wolfi base image holds its packages at the
  versions it shipped with, which kept `apk upgrade` from moving them, so a vulnerability fixed
  in one of them (CVE-2026-111497 in brotli) failed the image scan until the base was replaced.

## 0.0.2

### Added

- Instructions for running a published image directly with Docker, without cloning the source
  repository or building the image ([DOCS/quick-start.md](DOCS/quick-start.md)).

### Fixed

- Keep build provenance and SBOM attestations in GitHub's attestation store instead of publishing
  them as `sha256-...` registry tags that appear to be pullable images
  ([DOCS/releasing.md](DOCS/releasing.md)).

## 0.0.1

### Added

- The single container: nginx with TLS 1.3, the API, PostgreSQL 18 and the web app, built on
  Chainguard's Wolfi and hardened as described in [DOCS/security.md](DOCS/security.md).
- A status page showing whether the API and the database are up, with light and dark themes.
- `make` commands to run, update, back up, develop, test and check AresGate.
- Continuous integration: pytest, Vitest and Playwright (desktop and phone) with coverage,
  pyright, ESLint, SonarQube Cloud, CodeQL, Trivy, pip-audit, npm audit, zizmor and Dependabot.
- A workflow that publishes the image for amd64 and arm64 with signed provenance and an SBOM
  when a release is made ([DOCS/releasing.md](DOCS/releasing.md)).
- The README, these docs, and the security policy.
- The app secret key that will encrypt stored credentials and authenticator-app keys: the API
  won't start without one of at least 32 characters. The container makes it, or you supply it
  in `.env` or as a Docker secret ([DOCS/operations.md](DOCS/operations.md)).
- Setting up and signing in to the API: a one-time setup code in the container's log creates the
  one account, passwords are hashed with Argon2id and checked against a password policy,
  sign-ins are kept in `HttpOnly` `__Host-` cookies with a security token for every change, and
  wrong guesses lock the account, the address and the setup code for a growing wait
  ([DOCS/security.md](DOCS/security.md)).
- The web app's frame: a menu at the side that shrinks to icons (and remembers it), a bar at the
  bottom on a phone, a skip link for keyboards, and the page's title on top, in the light, dark
  ("mission control") and system themes.
- An audit log of sign-ins (and wrong guesses), sign-outs and setup, kept for a year
  (`ARESGATE_AUDIT_RETENTION_DAYS`), which the database refuses to change or delete, listed by
  `GET /api/audit/events` with filters ([DOCS/security.md](DOCS/security.md)).
- The web app's pages for these: setting up an account in two steps (the setup code, then a
  username and password), signing in and out, and a Security page with the account and its
  recent activity. Pages are closed to anyone who isn't signed in, and a sign-in that ends while
  a page is open sends you back to the sign-in page and on to where you were.
- A second step when signing in, with an authenticator app (RFC 6238 codes): the API makes a
  key to scan or type in, turns the step on once a code from the app proves it works, and gives
  ten single-use recovery codes. The key is encrypted with the app secret key, recovery codes
  are kept as keyed hashes, a code works once, and wrong codes count towards the same lockout
  as wrong passwords ([DOCS/security.md](DOCS/security.md)).
- The web app's pages for it: a Two-step verification card on the Security page to add an
  authenticator app (a QR code, a link for the same device and the key to type in), save the
  recovery codes, make new ones and turn it off, and a second step on the sign-in page that
  takes a code from the app or a recovery code. The activity list names the new events.
- `make two-factor-off ACCOUNT=<username>` turns an account's second step off for someone who
  has lost both the phone and the recovery codes. It ends the account's sign-ins and leaves an
  event in the audit log ([DOCS/operations.md](DOCS/operations.md)).
- An encrypted, write-only store for the credentials of integrations and AI providers: each is
  sealed with AES-256-GCM using a key made from the app secret key for its purpose and tied to
  its row, so a copy of the database reveals none of them. `PUT`, `DELETE` and `GET
  /api/credentials` store, forget and list them, and nothing returns a value. A refused request
  no longer quotes what it was sent. The pages that use it come with the integrations
  ([DOCS/security.md](DOCS/security.md)).
- `make rotate-secret-key` changes the app secret key and seals everything stored again with
  the new one, all or nothing, and leaves an event in the audit log. Recovery codes can't be
  carried over and are made again ([DOCS/operations.md](DOCS/operations.md)).
- Passkeys: sign in with a fingerprint, a face or a device's PIN with nothing typed. A passkey
  takes the place of the password and the authenticator app together (the device has to unlock
  it itself), belongs to the server name, and is checked against a one-time challenge and a
  sign-in count that must go up. The Security page adds and removes them (both ask for the
  password), the sign-in page has a "Sign in with a passkey" button, and the audit log records
  each ([DOCS/security.md](DOCS/security.md)).
- TLS certificates: `make cert` gets a Let's Encrypt certificate for the server name through the
  DNS challenge with an IONOS API key (using a pinned ACME client image, so nothing is installed),
  `make cert-renew` renews it when due and is meant for cron, and `make cert-reload` has nginx
  serve a changed certificate with no restart. A replacement is checked (key, name, expiry)
  before it is served. The container's health check already verifies the certificate as a
  browser would ([DOCS/quick-start.md](DOCS/quick-start.md#certificates)).
- Logs as JSON lines, one per request plus the API's own messages, each tagged with a request ID
  that nginx makes and that comes back in the `X-Request-ID` header, with secrets blanked out
  before anything is written ([DOCS/operations.md](DOCS/operations.md)). `ARESGATE_LOG_FORMAT`
  and `ARESGATE_LOG_LEVEL` change how and how much.
- `/api/system`, for someone signed in: AresGate's version, uptime and the database's version.
- Integration pages: one card for each of OPNsense, ntopng, Wazuh and CrowdSec showing what it
  provides, whether it is connected and when AresGate last reached it, and a page for each to
  connect, test and disconnect it. OPNsense's page finds the services that run on it (Suricata,
  CrowdSec, OpenVPN, WireGuard, IPsec, Unbound, Dnsmasq, Kea and more) and has an optional
  Zenarmor connection. Addresses must be on a private network and are never redirected, the
  certificate is checked (or trusted by a pasted authority or a pinned fingerprint), secrets are
  write-only, and every request is kept in an API log without secrets or query strings for
  `ARESGATE_API_LOG_RETENTION_DAYS` days ([DOCS/integrations.md](DOCS/integrations.md)).

- A Settings area in the web app, which replaces the Security page: **Account** (who is signed
  in, changing the password, passkeys and two-step verification), **Sign-ins** (the browsers that
  are signed in, with a button to sign out one or all the others) and **Activity**. Changing the
  password ends every other sign-in. The pages are tabs on a phone and a list at the side
  elsewhere ([DOCS/security.md](DOCS/security.md)).
- A **Status** page in the web app, and `GET /api/status` behind it, for when something seems
  wrong: AresGate's version, commit, build time and uptime, the versions of Python, nginx and
  PostgreSQL, the database's size, connections and migration, the TLS certificate browsers are
  shown and how long it has left, the container's CPUs, load, memory and disk, and the clock
  compared with the browser's. Each integration is listed as a part that works, has a problem or
  is off, with a link to its page, and anything that needs a look is said first. A card holds
  the same facts as text for a bug report, with addresses left out, and a button to copy it
  ([DOCS/operations.md](DOCS/operations.md#logs-and-health)).
- The image now records which commit it was built from and when (`make up` and the release
  workflow pass them in), so the Status page can say which build is running.
- The collector worker: a program of its own in the container, next to the API, that reads from
  the integrations on a schedule. Each job runs on its own timer for each connection, waits
  longer after every failure (30 seconds, then 1 minute, doubling up to its normal interval),
  stops after its timeout, and goes through the same client as the settings pages, so the
  address checks, certificate checks and API log are the same. The first job is a connection
  check every five minutes, which keeps an integration's status and the services found on it
  current without anyone pressing Test. Each job's last run, next run and last error are shown
  on the integration's page (a **Collection** card) and on the Status page, which also says
  whether the worker itself is running. `GET /api/collectors` has the same. Setting
  `ARESGATE_COLLECTORS_ENABLED=false` keeps the worker running but idle
  ([DOCS/operations.md](DOCS/operations.md#the-collector-worker)).
- Normalized event storage: what the collectors read is kept as events in one shape (time,
  integration, kind, severity, addresses and ports, the rule that fired, a summary, a hash that
  stops the same event being stored twice, and the program's own record), in a table for each
  week so old events leave by dropping a table. They are kept for 30 days
  (`ARESGATE_EVENT_RETENTION_DAYS`), or for as long as is set for an integration with
  `PUT /api/events/storage/<integration>`, and `GET /api/events/storage` says how many each has
  and how old the oldest is. The API removes the old ones when it starts and every six hours
  ([DOCS/operations.md](DOCS/operations.md#stored-events)).
- The first collector that stores events: OPNsense's firewall log, read every 30 seconds. Each
  line becomes an event with its time, the interface, what the firewall did (a block is low
  severity, anything else info), the direction, protocol, addresses and ports and the rule's
  description, and the line itself is kept beside it. The firewall's log has no time zone, so
  AresGate works the zone out from the firewall's clock and says so on the Collection card if the
  two clocks are more than five minutes apart instead of storing times it can't trust
  ([DOCS/integrations.md](DOCS/integrations.md#the-firewall-log)).
- OPNsense's Suricata alerts, read every minute when Suricata is installed: each alert becomes an
  event with its signature, interface, protocol, addresses and ports and whether Suricata
  blocked it (medium severity, or low if it did), and the record is kept beside it without the
  packet that set it off. Collectors now skip a service that testing the connection found isn't
  installed, so a firewall without Suricata has no such job
  ([DOCS/integrations.md](DOCS/integrations.md#suricata-alerts)).

### Fixed

- Signing in with a username containing a NUL character no longer ends in a server error.
