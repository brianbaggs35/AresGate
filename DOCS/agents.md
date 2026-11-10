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
| Exposure scanner | Tests your devices for services that should not be open. | Only when you start it |

Your own instructions are added to what a kind already does, and the AI is told that they come from
you. They can narrow what an agent cares about ("ignore routine scanning"); they cannot make it do
more than its kind can.

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

## For developers

- The graph and its nodes are in `backend/app/agents/graph.py`. Every call to LangGraph is in
  `backend/app/agents/flow.py`, so the rest of the code does not depend on its API.
- A kind is a template in `backend/app/agents/catalog.py`: what it looks at first, what more it may
  ask the model for, and how often it runs. Adding a kind adds no other code.
- The worker (`backend/app/agents/run.py`) starts the runs that are due, runs what waits and keeps
  every step in `agent_steps`. The API is in `backend/app/api/agents.py`.
- The tests' harness can run the agents when a test says, with the devices that "answer" chosen by
  the test: `POST /api/__test__/agents/run`, only in the end-to-end build.
