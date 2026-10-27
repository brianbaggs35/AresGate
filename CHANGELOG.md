# Changelog

Every release's notes are here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
