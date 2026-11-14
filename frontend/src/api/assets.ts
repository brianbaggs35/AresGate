import { apiDelete, apiGet, apiPut } from '@/api/client'
import type { IncidentStatus } from '@/api/incidents'
import type { VerdictKind } from '@/api/verdicts'
import type { Severity } from '@/severity'

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
  /** One of the firewall's own addresses, which all the traffic to and from the Internet crosses. */
  own: boolean
  /** What the owner said it is, if they did. */
  profile: AssetProfile | null
  /** What its name and maker suggest it is, which is only offered and never applied. */
  suggested_kind: string | null
  suggested_label: string | null
  /** What the device-fingerprinting service (Fingerbank) says it is, once it has been asked. */
  identity: AssetIdentity | null
}

/** What a device-fingerprinting service says a device is. */
export interface AssetIdentity {
  /** The integration that said so, and its name. */
  source: string
  source_name: string
  /** `unknown` when the service had no match for the hardware address. */
  state: 'identified' | 'unknown'
  /** Why it was asked: it is one of the owner's assets, or it is in an incident or threat. */
  reason: 'asset' | 'incident'
  /** The most specific thing it is, and the whole path to it, "Phone/Apple/iPhone". */
  name: string | null
  path: string | null
  manufacturer: string | null
  operating_system: string | null
  /** How sure the service is, from 0 to 100. */
  score: number | null
  checked_at: string
}

/** How much an asset matters to the owner: it ranks the threats that touch it. */
export const IMPORTANCES = ['normal', 'important', 'critical'] as const
export type Importance = (typeof IMPORTANCES)[number]

/** What the owner said an asset is, and what it is for. */
export interface AssetProfile {
  kind: string
  kind_label: string
  /** Whether it is a piece of the network itself, which carries other things' traffic. */
  carries: boolean
  purpose: string | null
  updated_at: string
  importance: Importance
}

/** One kind of asset the owner can pick. */
export interface AssetKind {
  key: string
  label: string
  group: string
  carries: boolean
  /** How much an asset of this kind usually matters, offered when it is picked. */
  importance: Importance
  /** Whether a threat that touched only assets of this kind takes more proof (guests, IoT). */
  lowers: boolean
}

/** The kinds that go together, such as the pieces of the network. */
export interface AssetKindGroup {
  key: string
  label: string
  kinds: AssetKind[]
}

/** How many assets the owner classified as one kind. */
export interface KindCount {
  key: string
  label: string
  count: number
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
  /** How many of all of them the owner classified as each kind, and how many they did not. */
  kinds: KindCount[]
  unclassified: number
}

/** What to ask for; what is left out is not narrowed. */
export interface AssetQuery {
  q?: string
  status?: AssetStatus
  sources?: readonly string[]
  interface?: number
  new?: boolean
  unidentified?: boolean
  /** A kind the owner said, or `unclassified` for those they have not classified. */
  kind?: string
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
  if (query.kind) params.set('kind', query.kind)
  if (query.sort) params.set('sort', query.sort)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const search = params.toString()
  return apiGet<AssetPage>(search ? `/assets?${search}` : '/assets')
}

/** An address the asset has had, and whether it has it now. */
export interface AssetAddress {
  address: string
  current: boolean
  first_seen_at: string
  last_seen_at: string
}

/** An interface whose networks hold one of the asset's addresses. */
export interface AssetNetwork {
  id: number
  name: string
}

/** An event one of the asset's addresses was in, as the program that reported it saw it. */
export interface AssetEvent {
  id: number
  occurred_at: string
  source: string
  source_name: string
  kind: string
  severity: Severity
  summary: string
  signature: string | null
  src_address: string | null
  src_port: number | null
  dst_address: string | null
  dst_port: number | null
  protocol: string | null
  /** Whether the asset sent it, rather than the one it was sent to. */
  outbound: boolean
}

/** A port at the far end of the asset's traffic with a peer. */
export interface AssetPort {
  port: number
  protocol: string | null
  /** How many events it was in with the asset, in the last week. */
  events: number
}

/** What threat intelligence has kept of a peer. Nothing is asked of a service to show it. */
export interface AssetStanding {
  /** What it comes to: the owner's ruling where there is one, else what the service made of it. */
  judgement: 'malicious' | 'suspicious' | 'clean' | 'unknown'
  /** What the service made of it, which a ruling does not change. */
  reported: 'malicious' | 'suspicious' | 'clean' | 'unknown'
  /** What the owner of the network ruled of it, and why, if they did. */
  ruling: 'safe' | 'suspicious' | null
  ruling_note: string | null
  malicious: number
  suspicious: number
  /** How many engines gave a verdict. */
  engines: number
  owner: string | null
  country: string | null
  /** When the service was last asked about it. */
  checked_at: string
}

/** Another address the asset's traffic went to, or came from. */
export interface AssetPeer {
  address: string
  /** How many events it was in with the asset, in the last week. */
  events: number
  last_seen_at: string
  /** The ports at the far end, the most often used first. */
  ports: AssetPort[]
  /** An address on a network of its own, which is never sent to a threat intelligence service. */
  internal: boolean
  /** What threat intelligence kept of it, or null if nothing is kept yet. */
  standing: AssetStanding | null
}

/** What was sent and received in a stretch of time, in bytes; null where nothing was measured. */
export interface AssetReading {
  at: string
  sent: number | null
  received: number | null
}

/** The asset's traffic as ntopng measured it. */
export interface AssetTraffic {
  /** Whether ntopng measured any of it. */
  measured: boolean
  /** The last day, by the hour. */
  hours: AssetReading[]
  /** The last week, by the day. */
  days: AssetReading[]
  sent_day: number
  received_day: number
  sent_week: number
  received_week: number
}

/** An incident one of the asset's addresses is in. */
export interface AssetIncident {
  id: number
  title: string
  severity: Severity
  confidence: number
  status: IncidentStatus
  verdict: string | null
  last_seen_at: string
  signal_count: number
  sources: string[]
}

/** A verdict the owner gave about one of the asset's addresses. */
export interface AssetVerdict {
  id: number
  verdict: VerdictKind
  address: string | null
  /** The network the device's traffic to it is about, when the verdict names one. */
  destination: string | null
  source: string | null
  signature: string | null
  note: string | null
  created_at: string
}

/** Everything AresGate knows of one asset. */
export interface AssetDetail {
  asset: Asset
  networks: AssetNetwork[]
  addresses: AssetAddress[]
  events: AssetEvent[]
  /** How many events its addresses were in, in the last day and in the last week. */
  events_day: number
  events_week: number
  talks_to: AssetPeer[]
  contacted_by: AssetPeer[]
  traffic: AssetTraffic
  incidents: AssetIncident[]
  verdicts: AssetVerdict[]
}

/** One asset's page, by its key: device-12 or host-3, as the Assets page links to it. */
export function fetchAsset(key: string): Promise<AssetDetail> {
  return apiGet<AssetDetail>(`/assets/${encodeURIComponent(key)}`)
}

/** The kinds of asset the owner can pick from, in groups. */
export function fetchKinds(): Promise<AssetKindGroup[]> {
  return apiGet<AssetKindGroup[]>('/assets/kinds')
}

/** Says what an asset is, what it is for and how much it matters, in place of what was said
 * before. */
export function classifyAsset(
  key: string,
  kind: string,
  purpose: string | null,
  importance: Importance,
  csrfToken: string,
): Promise<AssetProfile> {
  return apiPut<AssetProfile>(
    `/assets/${encodeURIComponent(key)}/profile`,
    { kind, purpose, importance },
    csrfToken,
  )
}

/** Takes back what was said of an asset. */
export function unclassifyAsset(key: string, csrfToken: string): Promise<undefined> {
  return apiDelete(`/assets/${encodeURIComponent(key)}/profile`, csrfToken)
}
