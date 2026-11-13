# Threats

A home network is scanned all day. A firewall, an intrusion detector and an agent on each machine
can between them raise tens of thousands of alerts in a day, and nearly all of it is the internet
knocking on doors that are shut. The **Threats** page is how AresGate keeps a real attack from
being lost in that: it counts each alert once, groups what belongs together, tells the real from the
routine, and shows you only the first. Nothing is thrown away. Every raw report is still on the
[Logs](operations.md#the-logs-page) page, and every incident is still on the Incidents page.

## From reports to threats

The top of the Threats page is a funnel. Each step takes something out, and says what.

| Step | What it counts |
| --- | --- |
| **Reports** | Every time a program (OPNsense, ntopng, Wazuh, CrowdSec) reported an alert. |
| **Alerts** | Reports with the duplicates taken out: an alert two programs both reported counts once, and the same alert again and again counts once for each stretch of time it happened in (an hour of the last 24 hours, six hours of the last 7 days). |
| **Incidents** | Alerts about the same thing, grouped: the same address (or the same block of addresses sweeping in waves) over the same period. |
| **Threats, suspects, background** | Where each incident stands, below. |

### The same alert, seen twice

OPNsense's intrusion detection, ntopng and Wazuh can each raise an alert about the very same
traffic. They are different detectors, and it matters that more than one agrees, so both are kept
and the incident lists them. But they are one alert. An alert is a *twin* of an earlier one when a
different program reported it within two minutes, about the same source and the same destination
(or the same port, where the firewall translated an address). The twin is marked, counted as a
duplicate, and an incident says how many of its alerts another program had already reported.

On the incident's page the twin is not an alert of its own: it is added to the first alert's
occurrence as a *confirmation*, which names the program, counts how often it agreed and keeps what
it said of the alert. The alert still counts once.

A program that reports a flow by its *reply* (the device talking back, which names the same two
addresses and ports the other way round) is matched too, so a firewall that logs the request and a
host agent that logs the answer are one alert. On the **Logs** page the first report says which
other programs reported it too (*Also reported by Wazuh and Suricata*), and each repeat says it is
the same alert as one already reported, so the list agrees with the incident: counted once, with
every program that saw it named.

### What each program said besides the basics

Every program says more than the columns an event keeps. `app/incidents/evidence.py` boils each
program's own record down to one shape: the rule's own facts (a Suricata signature number, a Wazuh
rule and level), words that sort the alert (a Wazuh rule's groups, a Suricata category), the MITRE
ATT&CK technique and tactic a Wazuh rule matched, what the alert names (a host, a URL, a DNS name, a
user, a country), the machine and the application, how much traffic the flow carried, and the log
line. It is kept with each signal (`incident_signals.evidence`, migration `0039`) because the
event's own record goes with the event's retention and an incident outlives it. Signals filed
before it was kept get it, a batch each run of the engine, while their events are stored.

The fields read are those the programs' documentation names; OPNsense returns Suricata's EVE record
flattened a little, so each member is looked for nested and with underscores or dots in its name.
ntopng's flow alerts are read as its alert list gives them (checked against a real answer): who the
client and the server are (name, country, whether the address is on your network or the internet,
whether ntopng has it on a blacklist), the ports and the service each is, the transport and the kind
of traffic, how long the flow lasted, how much each side sent, ntopng's own score, severity and
category, the technique it matched, its plain description and the flow's community ID. Suricata adds
the rule's own metadata (its severity, the product it is about, the technique), the certificate and
fingerprint of a TLS flow and, where OPNsense keeps the packet, what was sent. Wazuh adds what its
log names (addresses, ports, the command) and what its vulnerability detector found. What a version
leaves out is simply not shown. Migration `0042` has each signal read again for all of this, a
batch each run, while its event is stored.

### What was sent, and to whom

`app/incidents/conversations.py` groups the alerts of an incident by the two addresses, the port and
the protocol, which is what makes a conversation, and puts together what every program said of each
one: the first word any program said of an address (its name, country, location) is told of that
address everywhere, an address on any blacklist is on one, the biggest flow and the longest time any
program counted are kept, and what the traffic asked for (the name looked up, the site connected to)
is listed. Two programs that describe the same flow are one description, and a flow reported again
and again is one conversation with that many alerts. Where VirusTotal has been asked about an
address on the internet, what it said is on that end. The incident page draws each conversation as
its two ends with an arrow between them, the busiest first (**What was sent, and to whom**).

`app/incidents/coverage.py` says which of the integrations are not connected and what each would
add, so the page can say what is being missed and where to connect it (**What more connecting would
show**). The more integrations are connected, the more every part of the page has to show.

Where the owner has ruled an address safe or suspicious (see
[Correcting what VirusTotal says](integrations.md#correcting-what-virustotal-says)), that is what
the end shows, and what VirusTotal said stays beside it.

The AI is told all of it, a line to a conversation and a line to each technique, through the same
redaction as everything else, and its reading has *observations*: short statements of what stands
out in what was sent (migration `0042` adds `ai_triage.observations`).

`app/incidents/insights.py` adds it up for the whole incident, once for every alert (an alert two
programs both described counts what they said once): the techniques, the machines, the
applications, what was named, and for each program how many alerts it reported and what kinds of
detail it gave. The incident page draws it as *What the programs saw*. The more programs are
connected, the more it has to show.

### The same alert, again and again

A scanner that sweeps a port 3,000 times raises 3,000 alerts that say the same words about the same
two ends. On an incident they are one line with a count (**What kept happening**), on the dashboard
they are counted once per stretch of time, and the AI is never asked about them one at a time.

## Threat, suspect, background

Every incident that is going on is in one lane. (An incident you have handled, or one a verdict of
yours quiets, is in none: it is already dealt with.)

| Lane | Means |
| --- | --- |
| **Threat** | Highly likely to be a real attack. These are the only ones the dashboard puts in front of you as needing attention. |
| **Suspect** | Could be real, but AresGate is not sure enough to call it a threat. Worth a look when you have time. |
| **Background** | Scanning and probing that is part of life on the internet, or something AresGate cannot tell yet. Kept and searchable, and out of your way. |

What decides the lane, in this order:

1. **Your verdicts.** A verdict of yours always wins. A verdict can say where a device's traffic
   goes: a camera that calls its own cloud can be called normal for that network and nothing else
   it does. It matches only what the device sends there, so what the service sends back, and
   everything else the device does, still counts.
2. **How far the attack got.** Each alert is placed on a short path, the way Microsoft Sentinel's
   Fusion and Splunk's risk-based alerting look for several weak signs that add up: *looking
   around* (scans and probes), *trying to get in* (an exploit, an injection, a known
   vulnerability) and *a sign it worked* (malware, a command server, a web shell, a login that
   succeeded after many failures). Guessing passwords is none of them: botnets do it all day to
   everything. **An incident that went past looking around is a threat, and is never set aside**,
   whatever an AI thinks of it.
3. **How sure the rules are.** Every incident has a confidence from AresGate's rules. At or above
   *How sure before it is a threat* (65 until you change it) it is a threat. Below the floor of
   *Noise filters* (35) it is background. In between it is a suspect.
4. **What the AI makes of its kind** (below). An AI that is sure an incident is harmless can move
   it to the background; one that is sure it is an attack makes it a threat.

Every incident's page has a **Where it stands** card that says its lane and each fact that put it
there, one to a line, so you can check it and disagree.

### Attacks across two devices

An incident is about one address, so an attack that got into a device from the internet and then
made that device call out is two of them: the incident about the outside address that attacked, and
the one about the outside address the device then called (a beacon, a command server, a connection
it had no business making). Seen apart, the second looks like a device talking to the internet and
the first like an attempt. AresGate links them into a **chain**, the way Microsoft Sentinel's Fusion
does, by the device and the time between them and by nothing else:

- the attacker is an incident with an alert that is a flaw being tried (or a sign it worked), aimed
  at a device on your network;
- the callout is an incident with an alert the *device itself* sent to an address on the internet,
  at least medium serious, within six hours after that.

A link is **seen** when what the device sent is itself a sign that an attack worked (a beacon,
malware, a command server). It is **inferred** when the device only called out: the device and the
timing agree and nothing else does, so it is labelled as a guess and kept apart from what was seen.
Without an exploit aimed at the device there is no link at all, because scanning is what the
internet does to every address and calling out is what devices do: nothing is invented.

**A chain is a threat.** Its steps are never unsure and never set aside, whatever an AI thinks of
them alone. Chains are listed at the top of **Threats** and each has a page that draws the steps in
order, the device between the step that got in and the step that called out, with the evidence
behind each. An alert that two programs reported is shown once, with the programs that saw it. An
incident that is a step says so at the top of its page and leads to the whole attack.

### How it travelled, and what it was

An incident's page says more about the traffic than who and when:

- **How it travelled.** A traceroute lists the routers a packet crossed, but AresGate sends nothing
  out to find the way: a security tool that probes back is its own kind of problem, and it does not
  need to. Each program it reads sits at a known place between the internet and the device: the
  firewall at the edge, an intrusion detection system just behind it, a traffic monitor on the
  interface, a host agent on the device. The page draws the internet, each program that reported
  the incident in that order, and the device, with what each did about it (turned it away *n*
  times, stopped *n* alerts, banned the address). A program that did not report it is not on the
  path, so the path is only ever what was read. An attack that a device sent out is drawn the other
  way round. It runs across on a wide screen and down on a phone.
- **What it travelled through.** Under the path, the devices of the network it went through or
  touched, in the order it met them: the firewall that the internet's traffic crosses (first for an
  attack that came in, last for one that went out), the device it was about, then any other of your
  devices that turned up in it. Each is listed as the Assets page lists it, with what the owner said
  it is (a router, a camera) and what it is for. A device nobody has classified asks to be, and an
  address that no asset has says so. An incident about a rule with no address has nothing to list.
  What the owner said also goes to the analyst, which reads a camera calling a stranger differently
  from a laptop browsing.
- **What was said on the wire.** Under what it travelled through, a section of panels shows what
  Suricata read of the connections, where the firewall's intrusion detection is connected and the
  alert had it: the **certificate** a server showed (who it is for, who vouched for it, the dates,
  the way the connection was encrypted, and *Self-signed* or *Ran out* where that is so), a
  **web request** sent without encryption (method, host, address, software, the headers), the
  **names looked up** and what came back, the **banners of an ssh login**, and the start of the
  **packet** that set the alert off. What stands out is said first in plain words: a certificate
  that signed itself, one that has run out, a way of encrypting that is out of date (SSL 3, TLS 1.0
  or 1.1), a login or key sent as plain web traffic. The same certificate or request seen by many
  alerts is one, with how many alerts saw it. The section is left out when no program read any of
  it, and the analyst is told the same lines. A device such as a camera or a doorbell often shows a
  certificate it signed itself to the service it talks to, so the analyst is told that one on its
  own says little and is read beside what the device is for (see *What it travelled through*).
  Nothing that can be a secret is kept: the value of an `Authorization`, `Cookie` or API key
  header is replaced with *hidden* when the alert is read, and the start of a packet that has a
  password, a token or a key in it is not kept at all. Only the first 128 bytes and 400 characters
  of a packet are. `ARESGATE_KEEP_PACKETS=false` keeps no part of a packet at all (certificates,
  requests and lookups are still read).
- **What an address is called.** Where no program gave an address a name, AresGate asks the
  resolver the machine already uses for its reverse record (the name the address's owner gave it:
  `scanner-17.example.net` is a scanner, an `…compute.amazonaws.com` name is a rented server), and
  marks it *Name from DNS* so it is never mistaken for what a program said. It does so only for
  addresses on the internet, at most six to a page, waits two seconds at most, and keeps each
  answer for a week (a day where there was no name). It is the one lookup AresGate makes by itself;
  turn it off with `ARESGATE_REVERSE_DNS=false`.
- **What it was for.** From the application a program recognised, or the port, a conversation says
  in plain words what the traffic was for (*Logging in to a computer (SSH)*, *Looking up a name
  (DNS): example.com*). Nothing is read from inside the traffic, and nothing is said where nothing
  is known.
- **The first bytes of what was sent.** Where Suricata kept the packet, the first 128 bytes are
  shown as a hexadecimal dump beside the printable text, so the purpose of an alert can be read
  from what it carried.

## Kinds of incident

Hundreds of scanners from hundreds of addresses each make an incident of their own, because they
are different actors. But they are one *kind* of thing: the same program reported the same words
about the same sort of place. The **Kinds of incident** page (from the Threats page) lists them:

> Internet scanning: ET SCAN Potential SSH Scan, from the internet, 412 incidents from 380 addresses

A kind is named by the words of its incidents without the parts that differ (addresses and
numbers), where they came from (the internet, your own network, or a rule that names no address)
and which program saw them. Each has a page that says what is thought of it, why its incidents are
where they are and lists a few of them, with a link to all of them in Incidents.

### What the AI does with a kind

Reading every incident would be slow and costly, and would still leave you with the answers to
read. So the AI is asked about the *kind*, once: a few lines about each of up to twelve kinds in one
request, and one answer (noise, a probe, an attack, a compromise, or unclear, with how sure it is
and why) that covers every incident of that kind. That is what lets a scan be set aside without
anyone reading it, and why seventy thousand alerts cost a few questions.

- **It costs little.** The playbook and your setup notes come first in every request and are the
  same every time, so providers that cache a prompt's start (OpenAI and Anthropic) read them at a
  discount. A kind is asked about again only when it has grown a lot since, and a request that
  failed is not repeated for 15 minutes.
- **It follows your usage level.** On *Very low* the AI judges nothing by itself. *Low* asks one
  request an hour about kinds of 20 incidents or more, *Medium* two an hour (5 or more), *High*
  four (3 or more), *Maximum* eight (2 or more). You can always press **Ask the AI** on a kind.
  Spending limits are respected as before; see [AI providers](operations.md#ai-providers).
- **The provider sees stand-ins, not addresses.** Requests go through the redaction your AI
  settings choose, as everything else the AI reads does.
- **Its word is not final.** The AI's reading of one particular incident outranks its judgement of
  the kind, and **your word on a kind outranks both**: *Always background* sets every incident of it
  aside, whatever the AI says, and *Never set aside* keeps the AI from ever setting one aside.
  *Take my word back* undoes either.

### When a kind changes after it was judged

A kind that was harmless last month can come to include an exploit attempt, or reach a device it
never reached. So when a kind is judged, AresGate keeps what its incidents were like (their stages
of an attack, the destination ports, which of your devices they touch and how many addresses are
behind them), and compares it with what they are like now every few minutes, while the kind has
incidents going on. It counts as changed when:

- its incidents have a **stage of an attack** (looking around, trying to get in, a sign it worked) that
  they did not have,
- they reach a **destination port** or target a **device of yours** that they did not, but only for a
  kind that touched few (20 or fewer): one that already touches every port is not news,
- or there are **three times as many addresses** behind it, and at least 20 more.

A changed kind says so, with the reasons in words, on its card and at the top of its page. At the
next opportunity your usage level allows (any level but *Very low*, and never sooner than 15 minutes
after it was last judged) the AI is asked about it again, ahead of kinds that are only bigger, and is
told what changed and what it said before. A kind you have called stays yours: it is not judged
again, but its page says that it changed, so you can look again at your word on it. A kind with a
chain in it is never set aside, as before.

## Reviewing what the AI decided

The AI may sound an alarm on its own, but setting something aside is a decision you may want to
make, or at least to look at. The **Review** page (in the menu after Incidents) lists what the AI
called an incident, or a whole kind of incident, that would change what you see: a *possible
compromise* or an *active attack* (it raises the alarm) and a *probe* or *harmless* (it sets
things aside). Each card says what the AI called it and how sure it is, why, what that does if it
stands, and has **Agree** and **Disagree**, with an optional reason.

- **Where a decision stands.** It is *waiting for you*, *decided for you* (it counted at once, as
  you allowed) or answered. An agreed decision counts, a disagreed one never does, and
  **Take it back** sends an answer back to wait. A decision that waits counts only if it raises an
  alarm: nothing is set aside on the AI's word alone, unless you allow it.
- **How much waits** is **Settings > Review**. *Everything waits for me* is the default. *Only what
  the AI is unsure of* lets what it is at least *N*% sure of (50 to 100, 85 by default) count at
  once and sends the rest to you. *The AI decides on its own* counts everything at once, and the
  Review page still lists it, so you can disagree later. Decisions made before this existed count
  as the AI made them. The setting applies to what the AI decides from then on.
- **The AI learns from you.** The last few decisions you disagreed with, and your reasons, are
  added to what the AI is asked the next time it reads an incident or judges a kind (with
  addresses hidden as everywhere else). Turn it off with *Tell the AI what I disagreed with* in
  the same settings. Your reasons are kept in the database, not in the activity log.
- **Trust is earned.** Once you have answered 20 decisions and agreed with 95% of them, the page
  says the AI could be left to decide on its own, and links to the setting. Nothing changes
  until you change it.
- **Keep a kind.** Agreeing with a kind that was set aside has a box that keeps it so whatever the
  AI says next (the same as *Always background* on the kind's page), and disagreeing with it keeps
  it in front of you (*Never set aside*).
- **Where it shows.** The menu has a number for what waits, the dashboard says so and links to the
  page, and the incident and kind pages show where your review of the AI's call stands, with the
  same two buttons.

## Tuning it to your network

**Settings > Threat detection** is for fitting this to your setup. Nothing is kept until you press
**Save**, and as you change it the page works out what saving would do, the incidents that are going
on now moved between lanes, so you see the effect first.

| Setting | What it does |
| --- | --- |
| **How sure before it is a threat** | The confidence an incident has to reach to be a threat (5 to 100, 65 by default). Lower and more are called threats, and more of them turn out to be nothing. |
| **Let the AI set harmless incidents aside** | On by default. Probes and noise the AI is sure about go to the background instead of your list. They are still kept. |
| **How sure the AI has to be** | The AI's confidence needed to set one aside (50 to 100, 80 by default). Critical incidents are never set aside. |
| **A threat needs the AI to agree** | While an AI is on and reading by itself, an incident that only the rules are sure of is a suspect until the AI agrees (unless it is critical). |
| **What is open to the internet** | Nothing, some services (with their ports, up to 20) or not sure. The same scan means little on a network with nothing open and a lot on one that runs a service. The AI is told. |
| **Anything else about your network** | Up to 500 characters in your own words (a Plex server, a VPN to the office), which the AI is told too. |

The two AI settings do nothing while no AI is on; the page says so.

## Where it shows

- **Threats** is in the menu between the dashboard and Incidents, and on a phone in the bottom bar
  (Logs moved behind **More** to make room). It opens on the first lane with something in it.
- The **dashboard** says how many reports its alerts came from, puts only threats and suspects in
  *Needs you* (its link goes to Threats), and counts what the AI set aside.
- **Incidents** can be narrowed to a lane or a kind, each incident says its lane, and changing every
  incident that matches a search includes the lane and kind in it.
- A **kind** has its own page, and an incident links to its kind.

## For developers

The API, all under `/api` and signed in:

| | |
| --- | --- |
| `GET /threats/overview?window=24h\|7d` | The funnel, how many kinds the AI has judged, and the kinds with background incidents. |
| `GET /threats/families` | The kinds, narrowed by `lane`, `judged` (`ai`, `owner`, `waiting`) and `q`, a page at a time. |
| `GET /threats/families/{id}` | One kind: what is thought of it, why its incidents are where they are, and a sample. A kind carries `changed_at` and `changes` when it has changed since it was judged. |
| `PUT /threats/families/{id}/call` | Your word on a kind: `background`, `watch` or `null` to take it back. |
| `POST /threats/families/{id}/judge` | Has the AI judge the kind now. |
| `GET` and `PUT /threat-settings`, `POST /threat-settings/preview` | The settings, and what saving them would do. |
| `GET /incidents?lane=…&family=…` | The incident list takes repeatable `lane` and a `family`. |
| `GET /review?state=waiting\|decided\|answered` | The AI's decisions in one list (`limit`, `offset`), with the counts of all three, how often you agreed (`standing`) and the mode. |
| `GET /review/summary` | How many decisions wait, for the menu. |
| `POST /review/{incident\|family}/{id}` | Agree, disagree (with a `reason`, and `keep_kind` for a kind that was set aside) or `undo`. |
| `POST /review/agree` | Agrees with up to 100 decisions that still wait. |
| `GET` and `PUT /review/settings` | How much waits (`mode`, `auto_from`, `learn`). |
| `GET /threats/chains` | The attacks across two devices, the most recent first, narrowed by `confirmed`. |
| `GET /threats/chains/{id}` | One chain: its steps in order, each with its link (`confirmed` or `inferred`), why, and the evidence. |

Incident details also carry `path` (how it travelled), each conversation end a `name_from` (`program`
or `dns`) and each conversation a `purpose`, and the log list `twin_of` and `also_reported_by`.
The assistant and the agents can ask `who_is` (an address's reverse name) and `attack_chains`.

The code is in `app/threats/` (`families.py`, `stages.py`, `calls.py`, `explain.py`, `overview.py`,
`settings.py`, `drift.py`, which notices a kind that changed since it was judged, and `chains.py`, which links the incidents of an attack across two devices on
every run of the engine), `app/events/twins.py` (the same alert from two programs), `app/incidents/hops.py`, `names.py` and
`purpose.py` (how it travelled, what an address is called and what the traffic was for), `app/incidents/occurrences.py`
(repeats and confirmations), `app/incidents/evidence.py` and `insights.py` (what the programs said), `app/incidents/attention.py` (the lanes) and `app/ai/families.py` (the AI's judgement of
a kind). The lanes exist twice, as Python (`lane_of`) and as SQL (`lane_clauses`), and a test holds
them to agreeing. Migration `0028` adds the tables and columns, `0044` the chains and `0045` the names kept of
addresses. Migration `0047` adds `review` to the AI's readings and kind judgements, and the settings and
what you said (`app/review/`); a decision counts through `app/threats/calls.py` (`counts`), so the lanes
themselves did not change.

The Playwright harness can make attacks that are more than scanning (`exploit`, `compromise`), a
device that calls out instead of being called (`outbound`, which a chain needs on its second
incident) and
alerts a second program repeats (`twin`) and programs that say more than the basics (`detailed`) when it creates incidents; see
[the end-to-end tests' guide](../frontend/e2e/README.md).
