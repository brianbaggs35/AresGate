import type { Feed, Interface, Listing, Overview, Speed, Stats, Suggestion } from '@/api/interfaces'

/** Interfaces as the API describes them, for tests of pages that show them. */

export const feed = (overrides: Partial<Feed> = {}): Feed => ({
  id: 1,
  integration: 'opnsense',
  integration_name: 'OPNsense',
  connection: 'api',
  connection_label: 'REST API',
  native_name: 'igc0',
  label: '',
  detail: '',
  interface_id: null,
  ignored: false,
  last_seen_at: '2026-11-01T11:58:00Z',
  ...overrides,
})

export const iface = (overrides: Partial<Interface> = {}): Interface => ({
  id: 1,
  name: 'Internet',
  role: 'internet',
  notes: '',
  networks: [],
  position: 0,
  feeds: [],
  ...overrides,
})

export const suggestion = (overrides: Partial<Suggestion> = {}): Suggestion => ({
  name: 'Guests',
  role: 'guest',
  feed_ids: [2],
  reason: 'OPNsense igc2 and ntopng eth2 share a name.',
  interface_id: null,
  ...overrides,
})

export const listing = (overrides: Partial<Listing> = {}): Listing => ({
  interfaces: [],
  unplaced: [],
  ignored: [],
  suggestions: [],
  max_interfaces: 20,
  ...overrides,
})

export const speed = (overrides: Partial<Speed> = {}): Speed => ({
  source: 'opnsense',
  source_name: 'OPNsense',
  received: [null, 1_000_000, 2_000_000],
  sent: [null, 100_000, 400_000],
  ...overrides,
})

export const stats = (overrides: Partial<Stats> = {}): Stats => ({
  interface_id: 1,
  speed: speed(),
  alerts: 3,
  alerts_previous: 1,
  devices: 12,
  last_seen_at: '2026-11-01T11:59:00Z',
  ...overrides,
})

export const overview = (
  items: Stats[] = [stats()],
  overrides: Partial<Overview> = {},
): Overview => ({
  window: '24h',
  times: ['2026-11-01T10:00:00Z', '2026-11-01T10:15:00Z', '2026-11-01T10:30:00Z'],
  stats: items,
  ...overrides,
})
