# Alerts

Alerts are how AresGate tells you about a threat when you aren't looking at it. The **Alerts**
page in the menu sets up where they go. Today that is **Discord**: one channel of your own Discord
server, reached through a webhook. (Email and push notifications are planned; see the Jira
tickets the changelog names.)

This page is built in slices. What works today, and what comes next:

| | |
| --- | --- |
| Destinations: add, rename, turn off, remove, send a test message | Works |
| Rules for what is sent (only confident threats, filters, quiet hours, a rate limit), with a preview | Works |
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

## What a destination is told about

Each destination has its own rules, set from its card with **Rules**. A new destination starts with
the strictest sensible ones, because the point of an alert is that it is worth being woken for:
**medium or worse**, and only what AresGate is **at least 65% sure** of (the "high" band of the
Incidents page).

| Rule | What it does |
| --- | --- |
| How serious | The most serious thing in the incident: low, medium, high or critical. Info is never worth a message. |
| How sure AresGate is | High (65% or more), medium (35% or more) or any. |
| Reported by | Only incidents one of the chosen programs saw part of. Empty means any. |
| Kind of activity | Only incidents that include one of the chosen kinds (scanning, brute force). Empty means any. |
| Quiet hours | A start, an end (over midnight if the end is earlier), a time zone, and whether critical threats still get through. What came in during quiet hours is **held**, not dropped, and is sent when they end. |
| Limit | The most messages an hour. When more would come in, the rest are said in one summary. |
| Tell me again if it gets worse | A new message when an incident already sent becomes more serious or more certain. |
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

Whatever an attacker or a device can choose (an alert's words, a hostname) is put in a code span, so
it can't format the message, make a link or ping anyone, and `allowed_mentions` is empty on every
message anyway.

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

**Inferred, and not tried against Discord:** that a webhook sends the rate limit headers at all (the
page doesn't say which routes do, so the sender uses them only when they are there); that
`Retry-After` and `retry_after` mean the same; that `discordapp.com` still takes webhooks (the pages
name only `discord.com`); the character set of a token (the pages give none, so the check is
wide); that a wrong token answers `401` (the pages say only that `404` is a webhook that is
gone); that a `5xx` can be tried again; and that sending the `User-Agent` in that format is
enough for a webhook, which has no bot. The test message is how you find out on your own server.

## For developers

- `backend/app/alerts/discord.py` checks the address, builds messages and sends them;
  `backend/app/alerts/destinations.py` keeps destinations and their sealed addresses (credential
  kind `destination`, name `destination-<id>`); `backend/app/api/alerts.py` is the API under
  `/api/alerts/destinations`. `backend/app/alerts/rules.py` holds the rules and `decide()`, the one
  function that says whether an incident is sent to a destination, and the preview built on it;
  `PUT .../rules` replaces a destination's rules and `POST .../preview` previews a set of rules
  without saving them. The rules are columns of `alert_destinations` (migration 0025).
- `backend/app/alerts/notify.py` is the notifier: `decide_new` writes the outbox (`alert_deliveries`,
  migration 0029), `due_now` holds, limits and summarises, `plan` is one pass of deciding,
  `keep` records how a send went, and `run` is the loop the worker starts next to the collectors
  (off when collecting is, like the others). `backend/app/alerts/log.py` reads and prunes the log
  (`GET /api/alerts/deliveries`). The Playwright tests send alerts when a spec says, with
  `POST /api/__test__/notifier/run`.
- The Playwright tests point alerts at a Discord stand-in (`kind: "discord"` in the harness) with
  `app.state.alert_origin`; the product never does. The stand-in answers `204` for the one
  webhook it knows, `404 Unknown Webhook` for any other, and `403` to a request without Discord's
  `User-Agent`, and `GET /api/__test__/stand-ins/{id}/requests` returns what it was sent.
