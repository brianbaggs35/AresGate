import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client'
import type { Status } from '@/api/integrations'

export type Detail = 'brief' | 'standard' | 'full'

/** What decides what a destination is told of: `threats`, only the incidents on the Threats page
 * (a real attack going on now), or `custom`, what the severity, confidence, programs and kinds of
 * activity below choose. */
export type Mode = 'threats' | 'custom'

/** What a destination is told about, and when. The page always sends and receives the whole set. */
export interface Rules {
  mode: Mode
  /** The least serious it is told of, from 1 (low) to 4 (critical). */
  min_severity: number
  /** The least AresGate is sure, from 0 to 100. */
  min_confidence: number
  /** The programs it is told of, or none chosen for any. */
  sources: string[]
  /** The kinds of activity, `scan` and `brute_force`, or none chosen for any. */
  activities: string[]
  quiet_hours: boolean
  /** Minutes after midnight in `time_zone`. */
  quiet_from: number
  quiet_until: number
  /** Whether a critical incident is still sent in quiet hours. */
  quiet_critical: boolean
  time_zone: string
  max_per_hour: number
  detail: Detail
  again_when_worse: boolean
}

/** Something the rules can name, with what it is called. */
export interface Choice {
  key: string
  name: string
}

export interface Choices {
  sources: Choice[]
  activities: Choice[]
}

/** A place alerts are sent: a channel on the owner's Discord server, reached with a webhook, or an
 * email address, reached through the mail server. A webhook's address is a secret that only goes
 * in, so nothing here holds it. */
export type DestinationKind = 'discord' | 'email'

export interface Destination {
  id: number
  kind: DestinationKind
  name: string
  /** Sending to it is on. A destination that is off keeps its address and is sent nothing. */
  enabled: boolean
  /** Where it is, without the secret: a webhook's host, and the end of its number, or the mail
   * server's name (empty until the mail server is set up). */
  host: string
  hint: string
  /** Where an email destination's messages go, and none for a webhook. */
  recipient: string | null
  /** Not tried, working or failing. "Not connected" is a destination whose address is gone. */
  status: Status
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
  rules: Rules
  created_at: string
  updated_at: string
}

/** How the connection to the mail server is made: `starttls` starts plain and switches to
 * encryption, `ssl` is encrypted from the start, and `none` is never encrypted. */
export type Security = 'starttls' | 'ssl' | 'none'

/** The mail server that email destinations send through. The password only goes in, so all that is
 * said of it is whether one is kept. */
export interface MailServer {
  configured: boolean
  host: string
  port: number
  security: Security
  username: string | null
  sender: string
  password_kept: boolean
  /** The port that is usual for each way of connecting. */
  default_ports: Record<Security, number>
}

/** What the mail server's settings are saved as. A password left out stays as it is. */
export interface MailServerChange {
  host: string
  port: number
  security: Security
  username: string | null
  sender: string
  /** A new password. Never returned. */
  password?: string
  /** Forgets the password kept, for a server that needs none. */
  clear_password?: boolean
}

export interface Destinations {
  items: Destination[]
  /** The mail server email destinations send through. */
  smtp: MailServer
  /** How many may be kept. */
  max_destinations: number
  /** The hosts a webhook's address may be at. */
  hosts: string[]
  /** What the rules can name. */
  choices: Choices
}

/** Why incidents would have been left out, with the number. */
export interface LeftOut {
  reason: 'muted' | 'settled' | 'threat' | 'severity' | 'confidence' | 'source' | 'activity'
  text: string
  count: number
}

export interface PreviewExample {
  id: number
  title: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  confidence: number
  last_seen_at: string
}

/** What a set of rules would have done in the last day. */
export interface RulesPreview {
  hours: number
  /** The incidents going on in that time. */
  considered: number
  would_send: number
  /** Of those, how many quiet hours would have held back until they ended. */
  held: number
  /** The most that would have come in one hour, and how many the limit an hour would catch. */
  busiest_hour: number
  over_limit: number
  /** There were more incidents than could be looked at. */
  truncated: boolean
  left_out: LeftOut[]
  /** The newest few that would have been sent. */
  examples: PreviewExample[]
}

/** What a test message, or a sample alert, found. */
export interface DestinationTest {
  ok: boolean
  message: string
  destination: Destination
}

export type NewDestination =
  | {
      kind: 'discord'
      name: string
      /** The webhook's address, as Discord shows it. Never returned. */
      url: string
    }
  | { kind: 'email'; name: string; /** Where the messages go. */ recipient: string }

/** What can be changed of a destination. What is left out stays as it is. */
export interface DestinationChange {
  name?: string
  enabled?: boolean
  /** A new webhook address to replace the old. */
  url?: string
  /** A new email address to send to. */
  recipient?: string
}

export function fetchDestinations(): Promise<Destinations> {
  return apiGet<Destinations>('/alerts/destinations')
}

/** Keeps a new destination. It isn't tried yet: `testDestination` does that. */
export function addDestination(add: NewDestination, csrfToken: string): Promise<Destination> {
  return apiPost<Destination>('/alerts/destinations', add, csrfToken)
}

export function changeDestination(
  id: number,
  change: DestinationChange,
  csrfToken: string,
): Promise<Destination> {
  return apiPatch<Destination>(`/alerts/destinations/${id.toString()}`, change, csrfToken)
}

/** Forgets a destination and its address. */
export function removeDestination(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/alerts/destinations/${id.toString()}`, csrfToken)
}

/** Saves the mail server's settings, and answers how they are kept. */
export function saveMailServer(change: MailServerChange, csrfToken: string): Promise<MailServer> {
  return apiPut<MailServer>('/alerts/smtp', change, csrfToken)
}

/** Forgets the mail server and its password. Email destinations wait for another. */
export function removeMailServer(csrfToken: string): Promise<undefined> {
  return apiDelete('/alerts/smtp', csrfToken)
}

/** Sends a real test message, and answers how it went. */
export function testDestination(id: number, csrfToken: string): Promise<DestinationTest> {
  return apiPost<DestinationTest>(
    `/alerts/destinations/${id.toString()}/test`,
    undefined,
    csrfToken,
  )
}

/** Sends a sample alert, made up and marked as one, in the form this destination's rules give its
 * real messages, and answers how it went. */
export function sendSample(id: number, csrfToken: string): Promise<DestinationTest> {
  return apiPost<DestinationTest>(
    `/alerts/destinations/${id.toString()}/sample`,
    undefined,
    csrfToken,
  )
}

/** A field of a Discord embed. */
export interface EmbedField {
  name: string
  value: string
  inline: boolean
}

/** The embed of a message as Discord is sent it. */
export interface Embed {
  title: string
  description: string
  /** The colour of the bar beside it, as a number. */
  color: number
  url?: string
  footer?: { text: string }
  timestamp?: string
  fields?: EmbedField[]
}

/** A message as it is sent to a Discord webhook. */
export interface DiscordMessage {
  username: string
  embeds: Embed[]
}

/** Which message of the story of an incident a sample shows. */
export type SampleReason = 'new' | 'worse' | 'reopened'

export interface Sample {
  payload: DiscordMessage
}

/** What a message looks like, made by the code that makes the real ones about an incident that is
 * made up. */
export function fetchSample(
  mode: Mode,
  detail: Detail,
  reason: SampleReason = 'new',
): Promise<Sample> {
  const params = new URLSearchParams({ mode, detail, reason })
  return apiGet<Sample>(`/alerts/sample?${params.toString()}`)
}

/** Replaces what a destination is told about, and when. */
export function changeRules(id: number, rules: Rules, csrfToken: string): Promise<Destination> {
  return apiPut<Destination>(`/alerts/destinations/${id.toString()}/rules`, rules, csrfToken)
}

/** What these rules would have sent in the last day. Nothing is saved or sent. */
export function previewRules(id: number, rules: Rules, csrfToken: string): Promise<RulesPreview> {
  return apiPost<RulesPreview>(`/alerts/destinations/${id.toString()}/preview`, rules, csrfToken)
}

/** Where a message is: waiting (`queued`, `held` for quiet hours to end, `retrying` after a
 * failure, `limited` until a summary tells of it), told in a summary (`summarized`), `sent`, given
 * up on (`failed`), or no longer worth sending (`dropped`). */
export type DeliveryState =
  'queued' | 'held' | 'retrying' | 'limited' | 'summarized' | 'sent' | 'failed' | 'dropped'

/** Why a message was made: an incident the destination had not heard of, one that got worse (for a
 * destination told of threats, one that went a stage further), one that was reopened, a summary
 * of what was held back (over the limit, or in quiet hours), or a correction to a message sent
 * before (`retract`: it was stood down because the incident turned out not to be a threat). */
export type DeliveryReason = 'new' | 'worse' | 'reopened' | 'limit' | 'quiet' | 'retract'

/** One message to one destination, and what became of it. */
export interface Delivery {
  id: number
  destination_id: number
  destination: string
  /** None for a summary, and for a message whose incident has since been deleted. */
  incident_id: number | null
  /** `update` is a change to a message already sent. */
  kind: 'incident' | 'summary' | 'update'
  reason: DeliveryReason
  state: DeliveryState
  title: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  confidence: number
  /** For a summary, how many incidents it told of. */
  covers: number
  attempts: number
  created_at: string
  /** When it is due to be sent, or tried again. */
  due_at: string
  sent_at: string | null
  /** Why it is waiting, was not sent or failed, in words. */
  note: string | null
}

/** A page of the log, newest first. */
export interface Deliveries {
  items: Delivery[]
  /** The id to ask for the next page with, or none on the last. */
  next_before: number | null
  /** How many messages are in each state. */
  counts: Partial<Record<DeliveryState, number>>
}

/** What narrows the log. */
export interface DeliveryQuery {
  destination_id?: number
  state?: DeliveryState
  before?: number
}

/** The log of messages sent to destinations, what is waiting and what was held back or left out. */
export function fetchDeliveries(query: DeliveryQuery = {}): Promise<Deliveries> {
  const params = new URLSearchParams()
  if (query.destination_id !== undefined)
    params.set('destination_id', query.destination_id.toString())
  if (query.state !== undefined) params.set('state', query.state)
  if (query.before !== undefined) params.set('before', query.before.toString())
  const asked = params.toString()
  return apiGet<Deliveries>(asked ? `/alerts/deliveries?${asked}` : '/alerts/deliveries')
}
