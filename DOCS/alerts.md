# Alerts

Alerts are how AresGate tells you about a threat when you aren't looking at it. The **Alerts**
page in the menu sets up where they go: a **Discord** channel of your own server, reached through
a webhook, or an **email** address, reached through a mail server you set up once. (Push
notifications are planned; see the Jira tickets the changelog names.)

This page is built in slices. What works today, and what comes next:

| | |
| --- | --- |
| Destinations: add, rename, turn off, remove, send a test message | Works |
| Email destinations, through a mail server you set up (STARTTLS or SSL, with a password kept encrypted) | Works |
| Rules for what is sent (real attacks only, or filters of your own, quiet hours, a rate limit), with a preview | Works |
| Real-attack alerts that say why, tell again on escalation and are changed when they turn out harmless | Works |
| The sender, with de-duplication, retries and a delivery log | Works |
| A daily digest | Last |

## Setting up a Discord channel

1. In Discord, open your server's **Integrations** settings, choose **Webhooks**, make a webhook
   for the channel you want, and copy its URL. (Discord's own page is
   [Meet the Server Integrations Page](https://support.discord.com/hc/en-us/articles/360045093012);
   it says a server's Webhooks page lists the webhooks, lets you make new ones and copy a
   webhook's URL. It doesn't spell out the menu path, so the wording above is how it is done in the
   current app and may change.)
2. In AresGate, open **Alerts**, choose **Add destination**, give it a name and paste the
   address. It looks like `https://discord.com/api/webhooks/<number>/<token>`.
3. Choose **Send test message**. A message that says "AresGate can reach this channel" arrives in
   the channel, and the destination shows **Connected**. If it doesn't, the card says why in
   words: Discord doesn't accept the webhook (it was deleted, or its address changed), Discord is
   limiting how fast messages go, or Discord didn't answer.

A destination can be **turned off** without losing its address, **renamed**, given a **new
address**, or **removed**. Removing it forgets the address in AresGate. The webhook itself stays
in Discord until you delete it there.

## Setting up email

Email is a destination like a Discord channel: it has its own rules, a test message, a sample
alert and a place in the delivery log. What differs is how it is sent, so there are two steps.

1. **Set up the mail server** once, in the **Mail server** card under the destinations: its name
   (such as `smtp.example.com`), how the connection is made, the port, the user name and password
   it needs (if any) and the address the emails come from. Use your email provider's settings, or
   those of a server on your own network. If your provider offers an app password, use that.
   Choosing a way to connect fills in the usual port: **STARTTLS** is 587, **SSL/TLS** is 465
   and **none** is 25.
2. **Add the destination**: choose **Add destination**, then **Email**, give it a name and the
   address the alerts go to. It shows **Not connected** until the mail server is set up.

Then **Send test message** emails "AresGate can email you" to the address, and the destination
shows **Connected**. If it doesn't, the card says why in words: the server didn't accept the user
name and password, it refused the sender or the recipient, its certificate couldn't be verified,
it couldn't be reached, or it asked for the message to be tried again later.

An email is the same alert a Discord message is: the incident's title is the subject (with
`[AresGate]` in front, so you can filter it), and the description and the details are the text,
with a link back to the incident. The words that Discord would show in bold and as links are
written out as plain words. Unlike a Discord message, **an email can't be changed after it is
sent**, so one for an incident that later turns out to be harmless isn't followed by a correction:
the log shows only the one that was sent.

Saving the mail server settings, or giving a destination a new address, lets a destination that
had stopped after the server refused it try again. Removing the mail server forgets it and its
password; the email destinations stay, wait with **Not connected**, and send nothing until
another is set up.

## What a destination is told about

Each destination has its own rules, set from its card with **Rules**. The first choice is what
the channel is for, as three cards:

- **Real attacks only** (what a new destination starts with, and the recommended one). A message
  means something real is happening: an incident that is on the **Threats** page as a threat, an
  attack going on now. Scans, probes and background noise stay on that page. The severity,
  confidence, program and kind-of-activity rules below are not used for it, because what counts as
  a threat is already decided, in one place, by [Threats](threats.md) and **Settings > Threat
  detection**. See [Real attacks only](#real-attacks-only).
- **Everything serious.** Medium severity or worse, when AresGate is at least 65% sure (the "high"
  band of the Incidents page). More messages, including scans that are only looking around. This
  is what every destination got before there were two kinds of rule, and a destination made then
  keeps it.
- **Custom.** Choose how serious, how sure, which programs and which kinds of activity, below.

Quiet hours, the limit, "tell me again" and what a message says apply to all three.

| Rule | What it does |
| --- | --- |
| How serious | The most serious thing in the incident: low, medium, high or critical. Info is never worth a message. |
| How sure AresGate is | High (65% or more), medium (35% or more) or any. |
| Reported by | Only incidents one of the chosen programs saw part of. Empty means any. |
| Kind of activity | Only incidents that include one of the chosen kinds (scanning, brute force). Empty means any. |
| Quiet hours | A start, an end (over midnight if the end is earlier), a time zone, and whether critical threats still get through. What came in during quiet hours is **held**, not dropped, and is sent when they end. |
| Limit | The most messages an hour. When more would come in, the rest are said in one summary. |
| Tell me again if it gets worse (it escalates, for real attacks only) | A new message when an incident already sent becomes more serious or more certain; for real attacks only, when the attack goes a stage further. |
| What a message says | **Brief** (what happened, with a link, no addresses), **Standard** (adds the address on the internet and the programs that saw it) or **Full** (also names your devices; Discord keeps what is posted there, so only for a channel only you can read). |

**What no rule can change.** An incident you called *not suspicious* or *low priority* is never
sent, and neither is one you resolved or dismissed. An incident you called a *real threat* skips
the severity and confidence floors, since you have already decided, but still has to be from the
programs and of the kinds the rules name.

**The preview.** While the rules are open, the sheet shows what they would have done with the
last 24 hours: how many messages, how many would have waited for quiet hours or been put in a
summary by the limit, what was left out and why (each reason with its count), and the newest few
incidents that would have been sent, each linking to its page. It asks the server, which runs the
same function the sender uses, so the preview and what is sent cannot differ. The count of what a
limit would have summarised is rough: it goes by when each incident began, not by when it first met
the rules. It looks at the newest 2,000 incidents and says so when there were more. Nothing is sent
or saved by a preview.

## Real attacks only

A destination on **Real attacks only** is told of an incident when it **becomes a threat**, using
the same test as the Threats page (`attention.is_threat`, with the settings of **Settings > Threat
detection**), so what the page calls a threat and what a channel is told of cannot differ.

- **The message says why.** Its title is the furthest the attack got (*Attack in progress*,
  *Possible break-in* or *Threat*) and the incident's address; the body says how sure AresGate is
  and lists the facts that put it on the Threats page, in the words of the incident's own page
  (**Why AresGate thinks so**); and its fields give how far it got (*Looking around → **Trying to
  get in***), how sure, how serious, where it came from (Standard and Full), and at Full the
  devices on your network and what the strongest alert said. What a message says still follows the
  destination's detail setting.
- **Tell me again if it escalates.** An attack is told once, and again only when it goes a stage
  further: from looking around to trying to get in, or from there to a sign that it worked. A
  higher severity or a little more confidence alone is not an escalation. That second message
  starts *Escalated:*. (Switching a channel from *Custom* to *Real attacks only* may send one
  such message for an attack already told of, because the count of how far it got is new.)
- **A warning never stays up for nothing.** When an incident that was told of stops being a threat
  because you called it *not suspicious* or *low priority*, you resolved or dismissed it, or the AI
  set it aside as background, AresGate **changes the message it sent**: it becomes a grey *Stood
  down:* message that says so and why. If the same incident turns into a threat again, it is told
  of again as *Reopened:*, as a new message. Messages are looked at for 24 hours after they were
  sent. A message someone deleted in Discord is just left; the log says there was nothing to
  update, and the webhook is not blamed. Changing a message does not count toward the limit of
  messages an hour and is not held for quiet hours, since it only makes a standing warning less
  alarming.
- **Quiet hours and the limit still apply** to new messages, with the same summaries. A critical
  threat gets through quiet hours if that switch is on.
- **Nothing is sent that the other rules would not send.** An incident you called *not suspicious*
  or *low priority*, or resolved or dismissed, is never sent.

To make this possible AresGate asks Discord to say what it called each message it sends (the
`wait` option of Execute Webhook) and keeps that name with the log entry, so a message can be
found again. The log shows a change as **Stood down: ...** with the reason *Message changed:
stood down*.

### Seeing a message before it is sent

The Rules sheet draws the message as Discord will show it, with the colour bar, title, words,
fields and footer, and a choice of the **first message** or the one **if it escalates**. It is made
by the server with the same code that makes the real messages, about an incident that is made up,
so what is shown is what arrives; it changes at once when you change the card or how much a message
says. Its words are drawn as text, never as markup, and nothing in it is a link.

**Send a sample alert**, on a destination's card, sends that same made-up message to the channel,
with *sample alert* in its footer, so you can see it in Discord itself. It never touches the
log or the incidents, and it never repeats a real message: a sample is not an incident.

## What is sent, and when

The worker looks at the incidents every 30 seconds and, for each destination that is turned on, does
this:

1. **Decides what is new.** An incident the destination's rules choose is told **once**. It is told
   again only when it **gets worse** (a higher severity, or its confidence crosses into a higher
   band: low, medium or high), when "Tell me again if it gets worse" is on, or when you had
   resolved or dismissed it and it is **open again**. Each of those is one row in an outbox with a
   unique key, so a retry, a restart or a second pass never sends the same thing twice. A new
   destination hears only of what happens **after** it was added (or last turned on, or had its rules
   changed), not of the last few hours, and an incident that has not been seen for two hours is
   not news.
2. **Drops what you dealt with.** If you resolve, dismiss or call an incident *not suspicious* or
   *low priority* before its message went, the message is not sent, and the log says why.
3. **Holds, limits and summarises.** During quiet hours a message waits for them to end; if two or
   more waited, they are told as **one summary**. A destination hears of at most the number of
   messages an hour its rules allow, the worst first; the rest are told in **one summary an
   hour** ("7 incidents held back"), so a scan from a thousand addresses is one message and not a
   flood. A message that is still unsent two hours after it was due is given up on: it is no longer
   news.
4. **Sends,** one message at a time, a second apart. A message Discord answers with a fault, or with
   a limit, is **tried again** after 30 seconds, then twice as long each time up to a quarter of an
   hour, and as long as Discord's `retry_after` says if that is longer; after six tries it is
   given up on. A webhook Discord refuses (`401`, `403`, `404`: deleted, or a wrong token) is
   **never tried again**, because repeated refusals count against the address: the destination
   shows a problem, everything waiting for it is marked not sent, and nothing more goes there until
   you replace the address or a test message gets through.

What a message says depends on the destination's **detail** setting, and is built by
`backend/app/alerts/message.py`:

| Detail | A message says |
| --- | --- |
| Brief | How serious it is, what kind of thing (scanning, brute force), how sure AresGate is, and a link. No address and no name of anything on your network. |
| Standard | Adds the address it came from when that is on the internet, and the programs that saw it. |
| Full | Adds what the strongest alert said and the devices on your network it touched, by name. |

The table is for the wording; the parts are the same on both kinds of destination. A message to a
destination on **Everything serious** or **Custom** also carries the facts and the reasons that a
threat message does. Its fields give how far an attack got (when it went through stages), how sure,
how serious and, at Standard and Full, where it came from, and its body lists **Why AresGate thinks
so** in the words of the incident's own page, for example that the rules are 70% sure and the AI has
not judged it yet. So a message about something that is not (yet) a threat says how much it is worth
getting up for.

Whatever an attacker or a device can choose (an alert's words, a hostname) is put in a code span, so
it can't format the message, make a link or ping anyone, and `allowed_mentions` is empty on every
message anyway.

## When a collector goes quiet

An alert system that has stopped looking is worse than none, so a destination is also told when
a collector that was working **stops reporting**: the firewall's API stopped answering, a password
was changed, a service is down. A collector counts as quiet when it has not **worked** for fifteen
minutes or three of its own intervals, whichever is longer. One that has never worked is not
told of, because it has not gone quiet, it was never set up; the Status page shows it.

- It is told **once for each stretch of silence**, and again, in one short message, when the
  collector **works again**, but only if the first message was sent.
- It follows the destination's **quiet hours** like any message, and a quiet message that was
  still waiting when the collector came back is dropped, not sent late. Where quiet hours let
  critical incidents through, it goes through too.
- It is **not** counted against the messages an hour a destination allows, and it does not
  depend on the destination's rules: a destination that is on hears of every collector.
- Each one is a row in the delivery log, with the collector's name where an incident's title would
  be, and a link to the Status page in the message.

The worker runs the collectors and sends the messages, so a **stopped worker cannot tell you it has
stopped**. The watchdog catches a collector that fails while the worker lives. For the worker
itself, watch the container (`/api/health`, or your own monitoring).

## The delivery log

The **Delivery log** on the Alerts page lists every message, newest first, with where it is:
**Sent**, **Waiting to be sent**, **Held for quiet hours**, **Will try again**, **Held back by the
limit**, **Told in a summary**, **Not sent** or **Left out**, with the reason in words, the number
of tries and a link to the incident. It can be narrowed to a destination or a state, and old entries
are deleted after 30 days (`ARESGATE_ALERT_LOG_RETENTION_DAYS`, 1 to 365); what is still waiting is
never deleted. The log holds the incident's title, not what the message said.

A message is sent **at least once**: if the worker stops after Discord took a message and before the
log was saved, it is sent again when the worker starts.

## The address is a secret

Anyone who has a webhook's address can post to the channel, with no other sign-in. So:

- It is **sealed** with the app secret key like the other credentials (see
  [Security](security.md)), only the code that sends opens it, and **no route returns it**. The
  page shows the host and the end of the webhook's number (`discord.com/api/webhooks/…6789/••••••••`),
  never the token. Changing a destination leaves the address empty to keep the one saved.
- It is **checked three times**: when you type it, again every time it is opened to send (the
  credential store takes any text, so a stored address that isn't Discord's is refused rather
  than sent to), and by the network guard.
- Only **`discord.com` and `discordapp.com`** are accepted, over `https` on the standard port, with
  no user name, query or fragment, and a path of exactly `/api/webhooks/<number>/<token>` (a
  version, as in `/api/v10/webhooks/…`, is allowed). Anything else is refused in words that
  never repeat what was typed. There is no setting for other hosts: AresGate sends alerts to
  nowhere else.
- The request goes through the same **network guard** as AI providers: the host is looked up
  once, every address it leads to must be on the internet (never the home network, the machine
  itself or a cloud metadata address), the connection is made to the address that was checked,
  the certificate is verified and a redirect is never followed.
- The **API log** keeps each request without its address (`POST /api/webhooks/…`), and the token
  is replaced wherever it would turn up in an error message. The audit log says that a
  destination was added, changed, removed or tested, and names it, but never holds the address.

## The mail server and its password

The password lets anyone who has it send mail as you, so it gets the same care as a webhook's
address:

- It is **sealed** with the app secret key like the other credentials (see
  [Security](security.md)), only the code that sends opens it, and **no route returns it**: the
  page says only that one is kept. Saving the settings with the password left empty keeps the one
  saved; **Forget the saved password** removes it, for a server that needs none. The audit log
  says that the mail server was changed or removed, and names its host, but never holds the
  password.
- **A user name and password are only sent over an encrypted connection.** STARTTLS and SSL
  check the server's certificate against the system's authorities, and AresGate refuses to save a
  user name or password with the connection set to **none**. A server on your own network that
  needs no sign-in can be used without encryption.
- The server's address is checked before every connection, like a webhook's: it may be on the
  internet or on your home network (a relay is often either), but never this computer, a
  link-local address or a cloud provider's metadata service. Only the signed-in owner can set it,
  so the name is looked up and then connected to by name, which is not the same as the pinned
  connection the webhooks use.
- A connection that doesn't answer in 20 seconds is taken as unreachable, and tried again later.
  A server that refuses the sign-in, the sender or the recipient stops the destination until the
  settings or the address are fixed; a temporary refusal (a `4xx` answer) is tried again.

## What a message can contain

A message is a single Discord *embed*, kept inside Discord's limits (title 256, description
4096 characters), and sent with `"allowed_mentions": {"parse": []}` so that no text in it, however
it is worded, can ping `@everyone`, a role or a person. The test message says only where it came
from. Messages for incidents carry what the incident page already shows, with a link back to it, and
never a credential or a raw log line.

## Where this comes from, and what isn't tried

Built from Discord's developer documentation, read on 2026-11-01:

- [Execute Webhook](https://docs.discord.com/developers/resources/webhook): `POST
  /webhooks/{id}/{token}`, `content` up to 2000 characters, `embeds` up to 10, `wait=false`
  answers `204 No Content`, `allowed_mentions`, and "webhooks do not require a bot user or
  authentication to use".
- [Rate limits](https://docs.discord.com/developers/topics/rate-limits): a `429` carries
  `retry_after` in seconds (the page says to rely on that or the `Retry-After` header), and every
  answer may carry `X-RateLimit-Remaining` and `X-RateLimit-Reset-After`, which the sender uses to
  wait out a spent allowance before the next message; webhooks are limited per webhook; a webhook that answers `404`
  "should not" be used again; `401`, `403` and `429` count toward 10,000 invalid requests per ten
  minutes, past which the address is blocked for a while.
- [Message and embed limits](https://docs.discord.com/developers/resources/message), and the
  [API reference](https://docs.discord.com/developers/reference) (the base `https://discord.com/api`,
  the optional version, and the `User-Agent: DiscordBot ($url, $versionNumber)` format, without
  which requests "may be blocked").

- [Execute Webhook](https://docs.discord.com/developers/resources/webhook), again: `wait=true`
  "waits for server confirmation of message send before response, and returns the created message
  body", which has the message's `id`; and Edit Webhook Message, `PATCH
  /webhooks/{id}/{token}/messages/{message.id}`, which takes the same `embeds` and
  `allowed_mentions`.
- [JSON error codes](https://docs.discord.com/developers/topics/opcodes-and-status-codes): an error
  body has `code`; 10008 is "Unknown message" and 10015 "Unknown webhook".

**Inferred, and not tried against Discord:** that editing a message *replaces* its embed (the page
doesn't say, so the whole embed is sent again, with nothing added to it), that an edit of a deleted
message answers `404` with code 10008; and that a webhook sends the rate limit headers at all (the
page doesn't say which routes do, so the sender uses them only when they are there); that
`Retry-After` and `retry_after` mean the same; that `discordapp.com` still takes webhooks (the pages
name only `discord.com`); the character set of a token (the pages give none, so the check is
wide); that a wrong token answers `401` (the pages say only that `404` is a webhook that is
gone); that a `5xx` can be tried again; and that sending the `User-Agent` in that format is
enough for a webhook, which has no bot. The test message is how you find out on your own server.

**Email, inferred and not tried against a real provider:** that the usual ports are 587 for
STARTTLS and 465 for SSL, and 25 for a relay on your own network; that a refused sign-in is a
wrong user name or password (so it stops the destination, where other `5xx` answers only fail
that message), and that a `4xx` answer can be tried again. Python's `smtplib` does the talking. The test message is how you
find out with your own provider.

## For developers

- `backend/app/alerts/discord.py` checks the address, builds messages and sends them;
  `backend/app/alerts/destinations.py` keeps destinations and their sealed addresses (credential
  kind `destination`, name `destination-<id>`); `backend/app/api/alerts.py` is the API under
  `/api/alerts/destinations`. `backend/app/alerts/rules.py` holds the rules and `decide()`, the one
  function that says whether an incident is sent to a destination, and the preview built on it;
  `PUT .../rules` replaces a destination's rules and `POST .../preview` previews a set of rules
  without saving them. The rules are columns of `alert_destinations` (migration 0025).
- `backend/app/alerts/mail.py` checks the mail server's settings, turns a message built in
  Discord's form into an email (`render`) and sends it (`send`, which never raises: the answer is
  a `Sent`, like Discord's). The mail server is the one row of `smtp_settings` and its password
  is credential kind `smtp`, name `server` (migration 0051); an email destination is an
  `alert_destinations` row with kind `email` and a `recipient`. The API is `PUT` and `DELETE` on
  `/api/alerts/smtp`, and `GET /api/alerts/destinations` returns the settings (never the
  password) with the destinations.
- `backend/app/alerts/notify.py` is the notifier: `decide_new` writes the outbox (`alert_deliveries`,
  migration 0029), `due_now` holds, limits and summarises, `plan` is one pass of deciding,
  `keep` records how a send went, and `run` is the loop the worker starts next to the collectors
  (off when collecting is, like the others). `backend/app/alerts/log.py` reads and prunes the log
  (`GET /api/alerts/deliveries`). The Playwright tests send alerts when a spec says, with
  `POST /api/__test__/notifier/run`.
- Real attacks only: `backend/app/alerts/message.py` has `threat_message` and `stood_down_message`;
  `notify.py` keeps a threat's escalation as `worse:<rank>` with `THREAT_RANK + stages.depth()` and
  queues a change to a message as an `update` row (reason `retract`, `target_id` the row that sent
  it) which `notify_once` sends with `discord.edit`. Migration 0030 adds `alert_destinations.mode`
  and `alert_deliveries.message_id` and `target_id`. `GET /api/alerts/sample` makes the sample the
  Rules sheet draws and `POST /api/alerts/destinations/{id}/sample` sends it.
- The Playwright tests point alerts at a Discord stand-in (`kind: "discord"` in the harness) with
  `app.state.alert_origin`; the product never does. The stand-in answers `204` for the one webhook
  it knows (`200` with the message and its `id` when asked to `wait`, and it takes an edit of a
  message it made), `404 Unknown Webhook` for any other, `404` with code 10008 for a message it
  never made, and `403` to a request without Discord's `User-Agent`. `GET
  /api/__test__/stand-ins/{id}/requests` returns what it was sent.
