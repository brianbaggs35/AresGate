import { apiGet } from '@/api/client'

/** Whether a device is on the network: online now, listed within a day, or not for longer. */
export const ASSET_STATUSES = ['online', 'recent', 'away'] as const
export type AssetStatus = (typeof ASSET_STATUSES)[number]

/** How a list of assets is ordered: listed most recently first, by name, by address or newest. */
export const ASSET_SORTS = ['recent', 'name', 'address', 'first'] as const
export type AssetSort = (typeof ASSET_SORTS)[number]

/** One program listing an asset, and the way it did. */
export interface Listing {
  source: string
  source_name: string
  via: string
  /** The way, in words: the ARP table, DHCP leases. */
  via_label: string
  last_seen_at: string
  /** Whether being listed this way says it is on the network now. */
  presence: boolean
  /** For a machine with no hardware address that was merged into a device: by what. */
  matched_by: 'address' | 'hostname' | null
  /** For a machine, the program's word for how it is doing, such as active. */
  state: string | null
}

/** A device, or a machine that no device matched, as the connected programs together tell it. */
export interface Asset {
  /** What its page is at: device-12 or host-3. */
  key: string
  kind: 'device' | 'host'
  name: string
  hostname: string | null
  vendor: string | null
  mac: string | null
  /** The hardware address was made up by the device, as a phone does on Wi-Fi. */
  private_mac: boolean
  /** The addresses it has now, then the ones it had. */
  addresses: string[]
  current_addresses: number
  status: AssetStatus
  first_seen_at: string
  last_seen_at: string
  is_new: boolean
  /** Something says what it is: a name or a maker. */
  identified: boolean
  listings: Listing[]
  /** The ids of the interfaces whose networks hold one of its current addresses. */
  interfaces: number[]
}

/** A program that can list devices. */
export interface Supplier {
  key: string
  name: string
  /** Everything it needs is set up. */
  connected: boolean
  /** What it lists, such as the ARP table. */
  ways: string[]
  /** How many assets it lists, in all. */
  assets: number
}

/** An interface that has networks to tell which assets are on it. */
export interface InterfaceChoice {
  id: number
  name: string
  assets: number
}

/** How many assets are in each state, with every choice made but the state. */
export interface Counts {
  all: number
  online: number
  recent: number
  away: number
}

export interface AssetPage {
  total: number
  items: Asset[]
  counts: Counts
  suppliers: Supplier[]
  interfaces: InterfaceChoice[]
  /** How many of all of them each filter would find. */
  new: number
  unidentified: number
  /** When the first asset was first listed; null while there is none. */
  watching_since: string | null
  /** How many are on the Internet side (the provider's equipment, say), so not in the list. */
  outside: number
}

/** What to ask for; what is left out is not narrowed. */
export interface AssetQuery {
  q?: string
  status?: AssetStatus
  sources?: readonly string[]
  interface?: number
  new?: boolean
  unidentified?: boolean
  sort?: AssetSort
  limit?: number
  offset?: number
}

/** The assets that match, the ones listed most recently first unless asked for another order. */
export function fetchAssets(query: AssetQuery = {}): Promise<AssetPage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.status) params.set('status', query.status)
  for (const source of query.sources ?? []) params.append('source', source)
  if (query.interface) params.set('interface', query.interface.toString())
  if (query.new) params.set('new', 'true')
  if (query.unidentified) params.set('unidentified', 'true')
  if (query.sort) params.set('sort', query.sort)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const search = params.toString()
  return apiGet<AssetPage>(search ? `/assets?${search}` : '/assets')
}
