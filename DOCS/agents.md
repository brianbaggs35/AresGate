# Agents

An agent is a standing instruction to look at your network in a certain way. It runs on a
schedule or when you ask, reads what AresGate already knows, asks the AI what it makes of it, and
reports what is worth your attention. You make one from a kind, give it a name and, if you like,
your own instructions, and follow each run step by step on its page.

Agents are in the menu under **Agents**. AI has to be on for an agent to think: without it an
agent still looks, but it only keeps what it saw, and the page says why the AI could not read it.

## The kinds

| Kind | What it does | By default |
| --- | --- | --- |
| Threat hunter | Reads the open incidents, the latest alerts and who the firewall turned away most, follows up on what looks wrong, and says what, if anything, needs you. | Every hour |
| Intelligence analyst | Checks who is behind the traffic against what VirusTotal has reported (it reads what AresGate kept; it asks VirusTotal nothing). | Every 6 hours |
| Health watch | Notices when an integration or a collector stops working. | Every 2 hours |
| Noise cleaner | Finds duplicate, stale and noisy incidents across your integrations and suggests tidying them. | Every 6 hours |
| Exposure scanner | Tests your devices for services that should not be open. | Only when you start it |

Your own instructions are added to what a kind already does, and the AI is told that they come from
you. They can narrow what an agent cares about ("ignore routine scanning"); they cannot make it do
more than its kind can.

## What each kind needs

A kind is only as good as what AresGate can show it, so each one says what it needs and whether it
is there. The sheet that makes an agent, the Agents page and the agent's own page show a check for
each: an AI for the agents to ask (Settings > Agents), an alert source such as OPNsense or Wazuh, a
VirusTotal key for the intelligence analyst, known devices for the exposure scanner. A missing one
says what to do and links to where, and *How to set it up* lists the steps for the kind. An agent
whose kind is not ready is marked *It needs a little setup first* on its card. It can still run;
it just has less to read.

## What an agent remembers

Each run is told what the agent's last finished run reported, its summary and the titles of its
findings, so that it says what has changed instead of saying it all again. A finding the last run
already raised is marked *Still open* and a new one *New*; two findings are the same when their
words are, whatever the capitals and punctuation. What the last run said is shown to a provider
only through the redaction level chosen under Settings > AI, like everything else a run says.

## Which AI the agents use, and what they cost

An agent may run every hour, so Settings > Agents gives the agents their own choice of AI:

- **The same as Settings > AI** (the default): they ask whichever provider you chose there, while
  AI is turned on there.
- **A provider of their own**: choose one of the providers on Settings > AI (or set one up right
  there, key and all) and, if you like, a model for the agents, such as a cheaper one than you ask
  questions of. This works even while AI is off for everything else.
- **None**: they still look at your network and keep what they saw, but no AI reads it.

What a provider is shown does not change with this: it is the level chosen under Settings > AI,
for every use of the AI.

The agents' spending has a daily and a monthly limit of its own. When one is used up the agents
stop asking a provider that charges by the token, and carry on looking, until spending is back
under it. A provider on your own computer costs nothing and is never stopped. The limits on the
AI usage page still hold everything, the agents included.

Every run keeps what it used: requests, tokens (and how many of them the provider already had
cached), what that cost and which model answered. An agent's page shows the last 30 days, and the
Agents page adds all the agents up. Every request is also recorded as the provider saw it on the
AI usage page, under *Agents*.

## How a run works

Every run is a graph, built with [LangGraph](https://langchain-ai.github.io/langgraph/), that the
page draws as it goes:

1. **Plan** decides what to look at first.
2. **Look** reads what AresGate knows, with the same read-only tools the assistant has.
3. **Think** asks the AI what it makes of what was read. It may ask to look at more, and the graph
   goes back to Look. A run looks at most three rounds, and at most four things at a time.
4. **Report** settles a summary and the findings.

The graph the page draws is the one the API describes, so a change to what an agent does changes
the picture with no change to the page. Each step is kept as it happens: a step that looked at
something can be opened to read what it saw, in the words you read. What was sent to the AI
provider, redacted, is on the AI usage page, as it is for every request.

A run is asked for by you or by an agent's schedule and waits until the worker starts it, so
nothing is lost if the worker is not running at the time. One run of an agent goes at a time. A run
is ended after 15 minutes, a run that was going when the worker stopped is ended as interrupted
the next time it starts, and you can stop a run from its page. Runs and what they found are kept 30
days.

An agent only reads. It cannot change anything in AresGate or on your network, and the AI is told
that it must never say that it did.

## The exposure scanner

The scanner is the one agent that reaches out, so it has more rules than the rest:

- **You allow it.** It does nothing until you edit the agent and allow it to test your network, and
  it is never on a schedule. A run is always one you started.
- **It connects and nothing more.** For a short list of risky ports (FTP, Telnet, file sharing,
  Remote Desktop, VNC, databases and a few others) it opens a connection to see whether something
  answers, closes it at once, and sends and reads nothing. It is the same as asking whether a door
  is locked, not trying to open it.
- **Only your own network.** It tests only the devices AresGate has seen in the last seven days, at
  their addresses on your private networks, never an address on the internet, and at most 32 devices
  in a run. Nobody who can write to an agent can point it at an address.
- **Findings, not alarms.** What answers is a finding with how much it matters and why, such as
  Telnet or a database open to the whole network. A service that is normal, such as a router's web
  page, is information only.

## Privacy

Nothing an agent does leaves your house except the questions to your AI provider, which go through
the same gateway as every other: addresses are replaced by stand-ins for a hosted provider, and
every request is recorded. LangGraph's tracing to LangSmith, a hosted service, is switched off in
the code and cannot be turned on from the environment.

## The noise cleaner

The noise cleaner is for the list that grows while you are not looking. Several programs report
the same attack in their own words, scans repeat for days, and the AI often knows an incident is
noise. Each run finds three kinds of thing, the same way every time and without the AI:

- **Duplicates**: open incidents with the same title. The most serious and most recent stays; the
  rest would be dismissed.
- **Old and quiet**: open incidents nothing has touched for three days. They would be marked
  resolved.
- **Noise the AI is sure of**: incidents the AI read and is at least 80% sure are noise. They
  would get a "not suspicious" verdict.

Nothing serious is ever suggested: an incident that is high or critical, one AresGate is sure
about (65% or more), or one that already has a verdict that quiets it is left alone. The AI only
gets to veto: it may name a suggestion to leave alone and say why, never add one or change what it
does.

What it finds is shown on the agent's page under *What it suggests tidying*, each with how sure it
is, the incidents it would change and what it would do to them. **Apply** does it, through the same
bulk changes the incident list has, and **Leave it** turns it down; neither is asked again unless
what is in it changes. Everything it did can be taken back with **Take it back**, which puts the
incidents as they were.

Under Settings > Agents, *Tidying up* lets the noise cleaner do the surest of it itself, at 80% or
more. What it did is on the Activity page and on the agent's page, and can be taken back like any
other suggestion. The default is to only suggest.

## For developers

- The graph and its nodes are in `backend/app/agents/graph.py`. Every call to LangGraph is in
  `backend/app/agents/flow.py`, so the rest of the code does not depend on its API.
- A kind is a template in `backend/app/agents/catalog.py`: what it looks at first, what more it may
  ask the model for, how often it runs, what it needs and the steps to set it up. Adding a kind
  adds no other code. What it needs are the checks in `backend/app/agents/readiness.py`.
- What a run can look at are the read-only tools in `backend/app/ai/tools.py`, which the assistant
  shares. A tool only reads: a test fails if its source adds, deletes or commits.
- The noise cleaner's candidates are found in `backend/app/incidents/cleanup.py` (plain queries,
  no AI) and recorded, applied, turned down and taken back in `backend/app/agents/proposals.py`,
  which calls `backend/app/incidents/bulk.py`, so a suggestion is undone like a bulk change. A
  suggestion is kept once per agent by its key (`agent_proposals`, migration `0041`).
- Which provider the agents ask is `backend/app/agents/settings.py`; the gateway
  (`backend/app/ai/gateway.py`) follows it for requests whose purpose is `agent`, and a run adds up
  what its requests used when it ends (`run._spent`).
- The worker (`backend/app/agents/run.py`) starts the runs that are due, runs what waits and keeps
  every step in `agent_steps`. The API is in `backend/app/api/agents.py`.
- The tests' harness can run the agents when a test says, with the devices that "answer" chosen by
  the test: `POST /api/__test__/agents/run`, only in the end-to-end build.
