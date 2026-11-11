# Trust

Trust is where you tell AresGate that something is fine. A camera that talks to its cloud, a
scanner of your own, a vendor's monitoring service: when one of them is flagged as a threat and you
know better, you trust it, and AresGate stops raising alarms about it. Everything you trust is in
one list, under **Trust** in the menu, where you can change it or take it back at any time.

## What a decision is

A decision says **what** is trusted and **how much**.

**What** is any of these, and a report has to match every one that is set:

| Part | Meaning |
| --- | --- |
| Address | What an alert is about or came from. An address on its own is everything about it. |
| Only what it sends to | With an address: only what that address sends to the destination (an address or a whole network such as `52.0.0.0/8`). An attack aimed *at* the device, and anything else it does, still counts. |
| Only as reported by | Limits the decision to one program: OPNsense, ntopng, Wazuh or CrowdSec. Left empty, it holds for every program. |
| Only the alert | The alert's exact name. Other alerts about the address still count. |

**How much** is one of two levels. *Safe* never raises an alarm and adds nothing to how sure
AresGate is. *Low priority* is worth a glance and is kept in the timeline, and never alarms.

A decision applies to the **signals**, not to a program, so it holds whichever program reports
them. An alert that OPNsense and Wazuh both reported is one alert, counted once, with both programs
shown, and trusting its address quiets it however many programs said it. Trust decisions are the
same thing as the *not suspicious* and *low priority* verdicts of [Threats](threats.md): a verdict
of yours always wins, and a decision made here shows in the list of verdicts too.

## Trusting from where you see it

A **Trust** button is next to what can be trusted:

- on the page of an **incident**, for the address it is about;
- on each end of a **conversation** on that page that is on the internet.

It asks which part to trust, narrowest first, so the safest choice is the one that is ready:

1. *Only what the device sends to the address*, where a device on your network is known to have
   sent to it (a camera's traffic to its cloud, say);
2. *Only the alert* that was raised, where there is one;
3. *Everything about the address*.

Then how much, and why. The answer takes effect at once for what is going on and from here on, and
the incident is judged again. **Trust something** on the Trust page does the same for something
that is not on the screen, with the whole form.

## The page

- A banner at the top says how trust works.
- Tiles count the decisions, how many are safe and low priority, and how many alerts they have kept
  from raising an alarm.
- Each row says what is trusted, how much, what it has kept quiet and when it was changed. Search
  finds a decision by what it says, its reason or its level. The button beside a row takes it back,
  after asking.
- Opening a row shows the **decision**: everything about it can be changed there (what it is about,
  how much and why), what it was applied to is listed incident by incident, and it can be taken back.
  Changing what it is about judges again the incidents it no longer reaches and those it now does.
  Saying the same as another decision is refused, so each thing has one.

Taking a decision back means what it covered is judged as if you had never said it, so it can raise
alarms again.

## What the AI suggests

Where the AI has read an incident and is sure (60 out of 100 or more) it is nothing to worry about,
and nothing trusts its address yet, it is offered at the top of the page with its reason. **Trust**
is your call and one press; **Look first** opens the incident. The AI never trusts anything itself.

The assistant and the agents can ask what you trust with the `trusted` lookup, and the noise cleaner
and the incident investigator use it, so that they do not suggest again what you already said.
They only read: trusting and taking back are always yours.

## The API

Everything above is available under `/api/trust` for someone signed in: `GET /trust` lists the
decisions, `GET /trust/suggestions` has what the AI would trust, `GET /trust/{id}` reads one with the
incidents it was applied to, `POST /trust` trusts, `PUT /trust/{id}` changes all of one and
`DELETE /trust/{id}` takes one back. Each change is recorded in the audit log.
