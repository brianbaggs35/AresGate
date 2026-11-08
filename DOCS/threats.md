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

1. **Your verdicts.** A verdict of yours always wins.
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
| `GET /threats/families/{id}` | One kind: what is thought of it, why its incidents are where they are, and a sample. |
| `PUT /threats/families/{id}/call` | Your word on a kind: `background`, `watch` or `null` to take it back. |
| `POST /threats/families/{id}/judge` | Has the AI judge the kind now. |
| `GET` and `PUT /threat-settings`, `POST /threat-settings/preview` | The settings, and what saving them would do. |
| `GET /incidents?lane=…&family=…` | The incident list takes repeatable `lane` and a `family`. |

The code is in `app/threats/` (`families.py`, `stages.py`, `calls.py`, `explain.py`, `overview.py`,
`settings.py`), `app/events/twins.py` (the same alert from two programs), `app/incidents/occurrences.py`
(repeats), `app/incidents/attention.py` (the lanes) and `app/ai/families.py` (the AI's judgement of
a kind). The lanes exist twice, as Python (`lane_of`) and as SQL (`lane_clauses`), and a test holds
them to agreeing. Migration `0028` adds the tables and columns.

The Playwright harness can make attacks that are more than scanning (`exploit`, `compromise`) and
alerts a second program repeats (`twin`) when it creates incidents; see
[the end-to-end tests' guide](../frontend/e2e/README.md).
