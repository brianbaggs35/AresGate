import { apiGet } from '@/api/client'
import type {
  AssetEvent,
  AssetIdentity,
  AssetPort,
  AssetProfile,
  AssetStanding,
} from '@/api/assets'
import type { Severity } from '@/severity'

/** Whose a device is: one of the home's own assets, another private address, or on the Internet. */
export const DEVICE_SCOPES = ['yours', 'local', 'outside'] as const
export type DeviceScope = (typeof DEVICE_SCOPES)[number]

/** Whether a device was connected to, or made a connection. */
export const DEVICE_DIRECTIONS = ['incoming', 'outgoing'] as const
export type DeviceDirection = (typeof DEVICE_DIRECTIONS)[number]

/** How a list of devices is ordered: seen most recently first, the busiest, or by address. */
export const DEVICE_SORTS = ['recent', 'busiest', 'address'] as const
export type DeviceSort = (typeof DEVICE_SORTS)[number]

/** The asset an address is, when the Assets list holds it. */
export interface DeviceAsset {
  key: string
  name: string
  vendor: string | null
  mac: string | null
  status: 'online' | 'recent' | 'away'
  /** One of the firewall's own addresses. */
  own: boolean
  profile: AssetProfile | null
  suggested_label: string | null
  /** What Fingerbank says it is, once it has been asked. */
  identity: AssetIdentity | null
}

/** An address and what it did over the last week. */
export interface Device {
  address: string
  scope: DeviceScope
  /** What its reverse lookup called it, when one is kept. */
  name: string | null
  asset: DeviceAsset | null
  /** Events that name it as the destination: connections made to it. */
  incoming: number
  /** Events that name it as the source: connections it made. */
  outgoing: number
  first_seen_at: string
  last_seen_at: string
  /** The ports of its connections, the most often used first. */
  ports: AssetPort[]
  protocols: string[]
  /** The incidents of the week it is in, and how serious the worst is. */
  incidents: { count: number; worst: Severity } | null
  /** What threat intelligence kept of it; nothing is asked of a service to show it. */
  standing: AssetStanding | null
}

export interface DevicePage {
  items: Device[]
  total: number
  /** How many there are of each scope, among those a search finds. */
  counts: { all: number; yours: number; local: number; outside: number }
  /** How many days the connections are read over. */
  days: number
  /** More addresses were seen than are read, so the list is the ones seen most recently. */
  capped: boolean
}

/** What to ask for; what is left out is not narrowed. */
export interface DeviceQuery {
  q?: string
  scope?: DeviceScope
  direction?: DeviceDirection
  flagged?: boolean
  sort?: DeviceSort
  limit?: number
  offset?: number
}

/** The devices that match, the ones seen most recently first unless asked for another order. */
export function fetchDevices(query: DeviceQuery = {}): Promise<DevicePage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.scope) params.set('scope', query.scope)
  if (query.direction) params.set('direction', query.direction)
  if (query.flagged) params.set('flagged', 'true')
  if (query.sort) params.set('sort', query.sort)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const search = params.toString()
  return apiGet<DevicePage>(search ? `/devices?${search}` : '/devices')
}

/** What one device did with one peer over one port. `outgoing` is the device connecting to the
 * peer, and the port is the one at the far end of that. */
export interface DeviceConnection {
  direction: DeviceDirection
  /** Null when the event did not say where the other end was. */
  peer: string | null
  port: number | null
  protocol: string | null
  events: number
  first_seen_at: string
  last_seen_at: string
}

/** An incident a device is in, and the kind of threat and the chain it belongs to. */
export interface DeviceIncident {
  id: number
  title: string
  severity: Severity
  confidence: number
  status: 'open' | 'investigating' | 'resolved' | 'dismissed'
  verdict: string | null
  last_seen_at: string
  signal_count: number
  sources: string[]
  family_id: number | null
  family_label: string | null
  chain_id: number | null
}

/** Everything AresGate knows of one device. */
export interface DeviceDetail {
  device: Device
  events_day: number
  events_week: number
  connections: DeviceConnection[]
  events: AssetEvent[]
  incidents: DeviceIncident[]
}

/** One device's page, by its address. */
export function fetchDevice(address: string): Promise<DeviceDetail> {
  return apiGet<DeviceDetail>(`/devices/${encodeURIComponent(address)}`)
}
