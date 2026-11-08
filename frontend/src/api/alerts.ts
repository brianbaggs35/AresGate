import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client'
import type { Status } from '@/api/integrations'

export type Detail = 'brief' | 'standard' | 'full'

/** What a destination is told about, and when. The page always sends and receives the whole set. */
export interface Rules {
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

/** A place alerts are sent: a channel on the owner's Discord server, reached with a webhook. The
 * webhook's address is a secret that only goes in, so nothing here holds it. */
export interface Destination {
  id: number
  kind: 'discord'
  name: string
  /** Sending to it is on. A destination that is off keeps its address and is sent nothing. */
  enabled: boolean
  /** Where it is, without the secret: the host, and the end of the webhook's number. */
  host: string
  hint: string
  /** Not tried, working or failing. "Not connected" is a destination whose address is gone. */
  status: Status
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
  rules: Rules
  created_at: string
  updated_at: string
}

export interface Destinations {
  items: Destination[]
  /** How many may be kept. */
  max_destinations: number
  /** The hosts a webhook's address may be at. */
  hosts: string[]
  /** What the rules can name. */
  choices: Choices
}

/** Why incidents would have been left out, with the number. */
export interface LeftOut {
  reason: 'muted' | 'settled' | 'severity' | 'confidence' | 'source' | 'activity'
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

/** What a test message found. */
export interface DestinationTest {
  ok: boolean
  message: string
  destination: Destination
}

export interface NewDestination {
  name: string
  /** The webhook's address, as Discord shows it. Never returned. */
  url: string
}

/** What can be changed of a destination. What is left out stays as it is. */
export interface DestinationChange {
  name?: string
  enabled?: boolean
  /** A new address to replace the old. */
  url?: string
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

/** Sends a real test message, and answers how it went. */
export function testDestination(id: number, csrfToken: string): Promise<DestinationTest> {
  return apiPost<DestinationTest>(
    `/alerts/destinations/${id.toString()}/test`,
    undefined,
    csrfToken,
  )
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

/** Why a message was made: an incident the destination had not heard of, one that got worse, one
 * that was reopened, or a summary of what was held back (over the limit, or in quiet hours). */
export type DeliveryReason = 'new' | 'worse' | 'reopened' | 'limit' | 'quiet'

/** One message to one destination, and what became of it. */
export interface Delivery {
  id: number
  destination_id: number
  destination: string
  /** None for a summary, and for a message whose incident has since been deleted. */
  incident_id: number | null
  kind: 'incident' | 'summary'
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
