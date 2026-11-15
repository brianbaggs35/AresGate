import { apiGet } from '@/api/client'

/** What a CVE's score comes to, or `unrated` while NVD gives it none. */
export const RATINGS = ['critical', 'high', 'medium', 'low', 'unrated'] as const
export type Rating = (typeof RATINGS)[number]

/** What NVD said of one CVE, and when AresGate asked. */
export interface Cve {
  cve_id: string
  /** `unknown` where NVD has no record of it yet. */
  state: 'found' | 'unknown'
  checked_at: string
  status: string | null
  published_at: string | null
  modified_at: string | null
  cvss_version: string | null
  score: number | null
  rating: Rating
  vector: string | null
  description: string | null
  weaknesses: string[]
  /** Whether CISA lists it as exploited in the wild, and what it says of that. */
  exploited: boolean
  exploited_on: string | null
  action_due: string | null
  required_action: string | null
  kev_name: string | null
  link: string
}

export interface CveCounts extends Record<Rating, number> {
  exploited: number
}

export interface CvePage {
  /** What NVD asks a service that shows its data to say. */
  notice: string
  total: number
  /** How many match the text of each rating, whichever rating was asked for. */
  counts: CveCounts
  items: Cve[]
}

export interface CveQuery {
  q?: string
  rating?: Rating | null
  exploited?: boolean
  limit?: number
  offset?: number
}

/** The CVEs NVD has answered about, the ones asked about most recently first. Reading them asks NVD
 * nothing. */
export function fetchCves(query: CveQuery = {}): Promise<CvePage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.rating) params.set('rating', query.rating)
  if (query.exploited) params.set('exploited', 'true')
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset) params.set('offset', String(query.offset))
  const search = params.toString()
  return apiGet<CvePage>(search ? `/threat-intel/cves?${search}` : '/threat-intel/cves')
}

/** What Fingerbank made of a device: it named it, had no match, or was never asked because the
 * hardware address is one the device made up. */
export const DEVICE_STATES = ['identified', 'unknown', 'private'] as const
export type DeviceState = (typeof DEVICE_STATES)[number]

export interface DeviceIntel {
  device_id: number
  mac: string
  hostname: string | null
  /** Who made its network card, from its hardware address. */
  vendor: string | null
  /** The address it was last listed with. */
  address: string | null
  state: DeviceState
  /** Why it was looked up: it is one of the owner's assets, or is in an incident. */
  reason: 'asset' | 'incident'
  name: string | null
  path: string | null
  manufacturer: string | null
  operating_system: string | null
  /** How sure Fingerbank is, from 0 to 100. */
  score: number | null
  checked_at: string
  last_seen_at: string
}

export interface DeviceIntelPage {
  total: number
  counts: Record<DeviceState, number>
  items: DeviceIntel[]
}

export interface DeviceIntelQuery {
  q?: string
  state?: DeviceState | null
  limit?: number
  offset?: number
}

/** What Fingerbank made of each device it was asked about. Reading it asks Fingerbank nothing. */
export function fetchDeviceIntel(query: DeviceIntelQuery = {}): Promise<DeviceIntelPage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.state) params.set('state', query.state)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset) params.set('offset', String(query.offset))
  const search = params.toString()
  return apiGet<DeviceIntelPage>(
    search ? `/threat-intel/devices?${search}` : '/threat-intel/devices',
  )
}
