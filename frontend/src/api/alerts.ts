import { apiDelete, apiGet, apiPatch, apiPost } from '@/api/client'
import type { Status } from '@/api/integrations'

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
  created_at: string
  updated_at: string
}

export interface Destinations {
  items: Destination[]
  /** How many may be kept. */
  max_destinations: number
  /** The hosts a webhook's address may be at. */
  hosts: string[]
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
