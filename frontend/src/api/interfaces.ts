import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client'

/** What a part of the network is for, which is what the rest of AresGate reasons from. */
export const ROLES = [
  'internet',
  'dmz',
  'home',
  'guest',
  'iot',
  'vpn',
  'management',
  'other',
] as const
export type Role = (typeof ROLES)[number]

/** One stream of data a program reports under a name of its own (OPNsense's `igc0`, ntopng's
 * `eth1`), or a whole connection that names none (CrowdSec's bans). */
export interface Feed {
  id: number
  integration: string
  /** What the integration and its connection are called on a page. */
  integration_name: string
  connection: string
  connection_label: string
  /** The name the program uses; empty for the whole connection. */
  native_name: string
  label: string
  detail: string
  interface_id: number | null
  ignored: boolean
  last_seen_at: string
}

/** A part of the network the owner named, and the feeds placed on it. */
export interface Interface {
  id: number
  name: string
  role: Role
  notes: string
  /** CIDR blocks, such as 192.168.20.0/24. */
  networks: string[]
  position: number
  feeds: Feed[]
}

/** A guess at where feeds belong, never applied until the owner confirms it. */
export interface Suggestion {
  name: string
  role: Role
  feed_ids: number[]
  reason: string
  /** The interface the feeds would join when one has that name; otherwise one would be made. */
  interface_id: number | null
}

export interface Listing {
  interfaces: Interface[]
  /** Feeds that were found and are not placed, and the ones set aside. */
  unplaced: Feed[]
  ignored: Feed[]
  suggestions: Suggestion[]
  max_interfaces: number
}

export type OverviewWindow = '24h' | '7d'

/** How fast data went through an interface in bits a second, a bucket at a time (null where
 * nothing is known), and which program measured it. */
export interface Speed {
  source: string
  source_name: string
  received: (number | null)[]
  sent: (number | null)[]
}

export interface Stats {
  interface_id: number
  speed: Speed | null
  alerts: number
  alerts_previous: number
  /** Devices with an address on its networks; null when it has no networks to look in. */
  devices: number | null
  last_seen_at: string | null
}

export interface Overview {
  window: OverviewWindow
  /** When each bucket of the speeds starts. */
  times: string[]
  stats: Stats[]
}

/** What is needed to make an interface. */
export interface InterfaceRequest {
  name: string
  role: Role
  notes?: string
  networks?: string[]
  /** Feeds to place on it as it is made. */
  feeds?: number[]
}

/** What can be changed of an interface; what is left out stays. */
export type InterfaceChange = Partial<Omit<InterfaceRequest, 'feeds'>> & { position?: number }

/** Where a feed goes: on an interface, set aside, or (with neither) back to not placed. */
export interface Placement {
  interface_id?: number | null
  ignored?: boolean
}

/** What looking for feeds found. */
export interface Discovery {
  new: number
  complete: boolean
  notes: string[]
}

export function fetchInterfaces(): Promise<Listing> {
  return apiGet<Listing>('/interfaces')
}

export function fetchOverview(window: OverviewWindow): Promise<Overview> {
  return apiGet<Overview>(`/interfaces/overview?window=${window}`)
}

export function createInterface(request: InterfaceRequest, csrfToken: string): Promise<Interface> {
  return apiPost<Interface>('/interfaces', request, csrfToken)
}

export function changeInterface(
  id: number,
  change: InterfaceChange,
  csrfToken: string,
): Promise<Interface> {
  return apiPatch<Interface>(`/interfaces/${id}`, change, csrfToken)
}

export function removeInterface(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/interfaces/${id}`, csrfToken)
}

export function placeFeed(id: number, placement: Placement, csrfToken: string): Promise<Feed> {
  return apiPut<Feed>(`/interfaces/feeds/${id}`, placement, csrfToken)
}

export function discoverFeeds(csrfToken: string): Promise<Discovery> {
  return apiPost<Discovery>('/interfaces/discover', undefined, csrfToken)
}
