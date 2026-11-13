import { Clock, Wifi, WifiOff } from '@lucide/vue'
import type { LocationQuery } from 'vue-router'
import type { IconProps } from 'vuetify'

import {
  ASSET_SORTS,
  ASSET_STATUSES,
  type Asset,
  type AssetEvent,
  type AssetIdentity,
  type AssetQuery,
  type AssetSort,
  type AssetStatus,
  type AssetTraffic,
  type AssetVerdict,
  type Listing,
} from '@/api/assets'
import { formatCount } from '@/format'

interface Look {
  label: string
  /** What it means, because the three are easy to mix up. */
  description: string
  /** A theme color; none for the quietest. */
  color: string | undefined
  icon: NonNullable<IconProps['icon']>
}

/** Never just a color: each also has its own icon and its name. */
export const STATUS: Readonly<Record<AssetStatus, Look>> = {
  online: {
    label: 'Online',
    description:
      "Listed in the last few minutes by something that can only list what is on the network now: the firewall's ARP table, an ntopng host or a Wazuh agent that is in touch.",
    color: 'success',
    icon: Wifi,
  },
  recent: {
    label: 'Seen recently',
    description:
      'Listed in the last day, but not by anything that says it is on the network now. A DHCP lease only says the address was given out, and it lasts after the device has gone.',
    color: 'info',
    icon: Clock,
  },
  away: {
    label: 'Not seen for a while',
    description: 'Nothing has listed it for more than a day.',
    color: undefined,
    icon: WifiOff,
  },
}

export const SORTS: readonly { value: AssetSort; label: string }[] = [
  { value: 'recent', label: 'Listed most recently' },
  { value: 'name', label: 'Name' },
  { value: 'address', label: 'Address' },
  { value: 'first', label: 'First listed' },
]

export const DEFAULT_SORT: AssetSort = 'recent'

/** What the list is narrowed to and how it is ordered. It lives in the address of the page. */
export interface Filters {
  /** Null for every state. */
  status: AssetStatus | null
  q: string
  sources: string[]
  interface: number | null
  new: boolean
  unidentified: boolean
  /** A kind the owner said, `unclassified`, or null for every kind. */
  kind: string | null
  sort: AssetSort
}

export const NO_FILTERS: Readonly<Filters> = {
  status: null,
  q: '',
  sources: [],
  interface: null,
  new: false,
  unidentified: false,
  kind: null,
  sort: DEFAULT_SORT,
}

/** The filters an address says. Anything in it that isn't one of the choices is ignored. */
export function filtersOf(query: LocationQuery): Filters {
  const one = (name: string) => {
    const value = query[name]
    return typeof value === 'string' ? value : ''
  }
  const many = (name: string) => {
    const value = query[name]
    return (Array.isArray(value) ? value : [value]).filter(
      (item): item is string => typeof item === 'string' && item !== '',
    )
  }
  const interfaceId = Number(one('interface'))
  return {
    status: ASSET_STATUSES.find((each) => each === one('status')) ?? null,
    q: one('q'),
    sources: [...new Set(many('source'))],
    interface: Number.isSafeInteger(interfaceId) && interfaceId > 0 ? interfaceId : null,
    new: one('new') === '1',
    unidentified: one('unidentified') === '1',
    kind: one('kind') || null,
    sort: ASSET_SORTS.find((each) => each === one('sort')) ?? DEFAULT_SORT,
  }
}

/** The address of the page for these filters: only what differs from showing everything. */
export function routeQuery(filters: Filters): Record<string, string | string[]> {
  const query: Record<string, string | string[]> = {}
  if (filters.status) query.status = filters.status
  if (filters.q.trim()) query.q = filters.q.trim()
  if (filters.sources.length) query.source = filters.sources
  if (filters.interface) query.interface = filters.interface.toString()
  if (filters.new) query.new = '1'
  if (filters.unidentified) query.unidentified = '1'
  if (filters.kind) query.kind = filters.kind
  if (filters.sort !== DEFAULT_SORT) query.sort = filters.sort
  return query
}

/** What to ask the API for. */
export function queryOf(filters: Filters, limit: number, offset = 0): AssetQuery {
  const q = filters.q.trim()
  return {
    ...(q ? { q } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    sources: filters.sources,
    ...(filters.interface ? { interface: filters.interface } : {}),
    new: filters.new,
    unidentified: filters.unidentified,
    ...(filters.kind ? { kind: filters.kind } : {}),
    sort: filters.sort,
    limit,
    offset,
  }
}

/** How many choices narrow the list besides its state (which has a control of its own). */
export function activeFilters(filters: Filters): number {
  return (
    Number(filters.q.trim() !== '') +
    filters.sources.length +
    Number(filters.interface !== null) +
    Number(filters.new) +
    Number(filters.unidentified) +
    Number(filters.kind !== null)
  )
}

/** The programs that listed an asset, each once with the ways it did. */
export interface Source {
  key: string
  name: string
  /** The ways, in words, each with how a machine was matched to the device when it was. */
  ways: string[]
  /** The latest time any of its ways listed it. */
  last_seen_at: string
}

export function sourcesOf(asset: Pick<Asset, 'listings'>): Source[] {
  const found = new Map<string, Source>()
  for (const listing of asset.listings) {
    const way = wayOf(listing)
    const known = found.get(listing.source)
    if (!known) {
      found.set(listing.source, {
        key: listing.source,
        name: listing.source_name,
        ways: [way],
        last_seen_at: listing.last_seen_at,
      })
    } else {
      known.ways.push(way)
      if (Date.parse(listing.last_seen_at) > Date.parse(known.last_seen_at)) {
        known.last_seen_at = listing.last_seen_at
      }
    }
  }
  return [...found.values()]
}

/** How one program listed an asset: "ARP table", or "Agent (matched by address)". */
export function wayOf(listing: Listing): string {
  return listing.matched_by
    ? `${listing.via_label} (matched by ${listing.matched_by})`
    : listing.via_label
}

/** Where an event went, or came from: the address and port, or that the address is not known. */
export function eventFlow(
  event: Pick<AssetEvent, 'outbound' | 'src_address' | 'src_port' | 'dst_address' | 'dst_port'>,
): string {
  const end = (address: string | null, port: number | null) => {
    if (address === null) return 'an unknown address'
    return port === null ? address : `${address}:${port}`
  }
  return event.outbound
    ? `To ${end(event.dst_address, event.dst_port)}`
    : `From ${end(event.src_address, event.src_port)}`
}

/** What a verdict is about, beyond its device: the destination, the alert, or else all it does. */
export function scopeOfVerdict(verdict: Pick<AssetVerdict, 'destination' | 'signature'>): string {
  const parts: string[] = []
  if (verdict.destination) parts.push(`its traffic to ${verdict.destination}`)
  if (verdict.signature) parts.push(`the alert "${verdict.signature}"`)
  return parts.length ? parts.join(' and ') : 'everything it does'
}

/** What a page is under the name of an asset: a device or a machine, then its maker and hardware
 * address when they are not already its name. */
export function descriptionOf(asset: Pick<Asset, 'kind' | 'name' | 'vendor' | 'mac'>): string {
  const parts = [asset.kind === 'host' ? 'Machine' : 'Device']
  if (asset.vendor && asset.vendor !== asset.name) parts.push(asset.vendor)
  if (asset.mac && asset.mac !== asset.name) parts.push(asset.mac)
  return parts.join(' · ')
}

/** The traffic of an asset as its chart shows it: by the hour for the last day, by the day for the
 * last week. A stretch nothing was measured in is a gap, not a zero. */
export function chartOf(
  traffic: Pick<AssetTraffic, 'hours' | 'days'>,
  range: '24h' | '7d',
): { times: number[]; series: { id: string; label: string; values: (number | null)[] }[] } {
  const readings = range === '24h' ? traffic.hours : traffic.days
  return {
    times: readings.map((item) => Date.parse(item.at)),
    series: [
      { id: 'sent', label: 'Sent', values: readings.map((item) => item.sent) },
      { id: 'received', label: 'Received', values: readings.map((item) => item.received) },
    ],
  }
}

/** What the events of an asset come to, in words, under their heading. */
export function eventsNoteOf(weekly: number): string {
  if (weekly === 0) return 'Nothing in the last week.'
  return `${formatCount(weekly)} in the last week, newest first.`
}

/** The addresses of an asset to show in a list: the ones it has now, up to a few, and how many
 * more there are. */
export function addressesOf(
  asset: Pick<Asset, 'addresses' | 'current_addresses'>,
  limit = 3,
): { shown: string[]; more: number } {
  const current = Math.max(asset.current_addresses, Math.min(1, asset.addresses.length))
  const shown = asset.addresses.slice(0, Math.min(current, limit))
  return { shown, more: asset.addresses.length - shown.length }
}

/** The steps of what Fingerbank says a device is, from the widest to the most specific:
 * `Phone, Tablet, or Wearable/Apple iOS/Apple iPhone` is three. A name with no path is one step. */
export function identitySteps(identity: Pick<AssetIdentity, 'name' | 'path'>): string[] {
  const steps = (identity.path ?? '')
    .split('/')
    .map((step) => step.trim())
    .filter(Boolean)
  if (steps.length) return steps
  return identity.name ? [identity.name] : []
}

/** How sure Fingerbank is, in words, by the bands its documentation gives its score: below 30 very
 * little, to 50 moderate, to 75 high and above that very high. */
export function identityConfidence(score: number): string {
  if (score < 31) return 'Low'
  if (score < 51) return 'Moderate'
  if (score < 76) return 'High'
  return 'Very high'
}
