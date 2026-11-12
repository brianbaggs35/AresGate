import type {
  Asset,
  AssetIdentity,
  AssetKindGroup,
  AssetPage,
  AssetProfile,
  Counts,
  Listing,
  Supplier,
} from '@/api/assets'

/** Assets as the API describes them, for tests of pages that show them. */

export const listed = (overrides: Partial<Listing> = {}): Listing => ({
  source: 'opnsense',
  source_name: 'OPNsense',
  via: 'arp',
  via_label: 'ARP table',
  last_seen_at: '2026-11-01T11:58:00Z',
  presence: true,
  matched_by: null,
  state: null,
  ...overrides,
})

/** What Fingerbank says a phone is. */
export const identity = (overrides: Partial<AssetIdentity> = {}): AssetIdentity => ({
  source: 'fingerbank',
  source_name: 'Fingerbank',
  state: 'identified',
  reason: 'asset',
  name: 'Apple iPhone 16',
  path: 'Phone, Tablet, or Wearable/Apple iOS, macOS, and tvOS/Apple iPhone/Apple iPhone 16',
  manufacturer: 'Apple, Inc.',
  operating_system: 'Apple iOS',
  score: 72,
  checked_at: '2026-11-01T11:00:00Z',
  ...overrides,
})

export const asset = (overrides: Partial<Asset> = {}): Asset => ({
  key: 'device-1',
  kind: 'device',
  name: 'Laptop',
  hostname: 'Laptop',
  vendor: 'Example Devices Inc.',
  mac: '00:11:22:0a:0b:0c',
  private_mac: false,
  addresses: ['192.168.1.20'],
  current_addresses: 1,
  status: 'online',
  first_seen_at: '2026-09-01T10:00:00Z',
  last_seen_at: '2026-11-01T11:58:00Z',
  is_new: false,
  identified: true,
  listings: [listed()],
  interfaces: [],
  own: false,
  profile: null,
  suggested_kind: null,
  suggested_label: null,
  identity: null,
  ...overrides,
})

/** A machine no device matched, as Wazuh lists its agents. */
export const machine = (overrides: Partial<Asset> = {}): Asset =>
  asset({
    key: 'host-3',
    kind: 'host',
    name: 'build-server',
    hostname: 'build-server',
    vendor: null,
    mac: null,
    addresses: ['192.168.1.50'],
    listings: [
      listed({
        source: 'wazuh',
        source_name: 'Wazuh',
        via: 'agent',
        via_label: 'Agent',
        state: 'active',
      }),
    ],
    ...overrides,
  })

export const supplier = (overrides: Partial<Supplier> = {}): Supplier => ({
  key: 'opnsense',
  name: 'OPNsense',
  connected: true,
  ways: ['ARP table', 'DHCP leases'],
  assets: 1,
  ...overrides,
})

export const counts = (overrides: Partial<Counts> = {}): Counts => ({
  all: 1,
  online: 1,
  recent: 0,
  away: 0,
  ...overrides,
})

export const page = (
  items: Asset[] = [asset()],
  overrides: Partial<AssetPage> = {},
): AssetPage => ({
  total: items.length,
  items,
  counts: counts({ all: items.length, online: items.length }),
  suppliers: [supplier({ assets: items.length })],
  interfaces: [],
  new: 0,
  unidentified: 0,
  watching_since: '2026-09-01T10:00:00Z',
  outside: 0,
  kinds: [],
  unclassified: items.length,
  ...overrides,
})

export const profile = (overrides: Partial<AssetProfile> = {}): AssetProfile => ({
  kind: 'camera',
  kind_label: 'Camera or doorbell',
  carries: false,
  purpose: 'Watches the front door',
  updated_at: '2026-11-12T10:00:00Z',
  ...overrides,
})

/** The kinds the owner can pick from, as a short list in two groups. */
export const kindGroups = (): AssetKindGroup[] => [
  {
    key: 'network',
    label: 'The network',
    kinds: [
      { key: 'router', label: 'Router', group: 'network', carries: true },
      { key: 'switch', label: 'Network switch', group: 'network', carries: true },
    ],
  },
  {
    key: 'home',
    label: 'Around the home',
    kinds: [{ key: 'camera', label: 'Camera or doorbell', group: 'home', carries: false }],
  },
]
