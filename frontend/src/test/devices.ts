import type { AssetStanding } from '@/api/assets'
import type {
  Device,
  DeviceAsset,
  DeviceConnection,
  DeviceDetail,
  DeviceIncident,
  DevicePage,
} from '@/api/devices'
import { event } from '@/test/assetDetail'

/** Devices as the API describes them, for tests of pages that show them. */

/** A server on the Internet that a laptop connected to, and nothing else is known of. */
export const device = (overrides: Partial<Device> = {}): Device => ({
  address: '52.1.2.3',
  scope: 'outside',
  name: null,
  asset: null,
  incoming: 3,
  outgoing: 1,
  first_seen_at: '2026-11-01T09:00:00Z',
  last_seen_at: '2026-11-01T11:50:00Z',
  ports: [{ port: 443, protocol: 'tcp', events: 4 }],
  protocols: ['tcp'],
  incidents: null,
  standing: null,
  ...overrides,
})

/** The asset an address of the home is. */
export const deviceAsset = (overrides: Partial<DeviceAsset> = {}): DeviceAsset => ({
  key: 'device-1',
  name: 'Laptop',
  vendor: 'Example Devices Inc.',
  mac: '00:11:22:0a:0b:0c',
  status: 'online',
  own: false,
  profile: null,
  suggested_label: null,
  identity: null,
  ...overrides,
})

/** One of the home's own devices. */
export const yours = (overrides: Partial<Device> = {}): Device =>
  device({
    address: '192.168.1.20',
    scope: 'yours',
    asset: deviceAsset(),
    incoming: 0,
    outgoing: 5,
    ...overrides,
  })

export const standing = (overrides: Partial<AssetStanding> = {}): AssetStanding => ({
  judgement: 'malicious',
  reported: 'malicious',
  ruling: null,
  ruling_note: null,
  malicious: 4,
  suspicious: 1,
  engines: 70,
  owner: 'Example Hosting',
  country: 'NL',
  checked_at: '2026-11-01T11:00:00Z',
  ...overrides,
})

export const connection = (overrides: Partial<DeviceConnection> = {}): DeviceConnection => ({
  direction: 'outgoing',
  peer: '52.1.2.3',
  port: 443,
  protocol: 'tcp',
  events: 3,
  first_seen_at: '2026-11-01T09:00:00Z',
  last_seen_at: '2026-11-01T11:50:00Z',
  ...overrides,
})

export const involved = (overrides: Partial<DeviceIncident> = {}): DeviceIncident => ({
  id: 7,
  title: 'Port scan from 52.1.2.3',
  severity: 'high',
  confidence: 80,
  status: 'open',
  verdict: null,
  last_seen_at: '2026-11-01T11:00:00Z',
  signal_count: 4,
  sources: ['opnsense'],
  family_id: 3,
  family_label: 'Port scan',
  chain_id: null,
  ...overrides,
})

export const devicePage = (
  items: Device[] = [device()],
  overrides: Partial<DevicePage> = {},
): DevicePage => ({
  items,
  total: items.length,
  counts: {
    all: items.length,
    yours: items.filter((item) => item.scope === 'yours').length,
    local: items.filter((item) => item.scope === 'local').length,
    outside: items.filter((item) => item.scope === 'outside').length,
  },
  days: 7,
  capped: false,
  ...overrides,
})

export const deviceDetail = (overrides: Partial<DeviceDetail> = {}): DeviceDetail => ({
  device: device(),
  events_day: 2,
  events_week: 4,
  connections: [connection()],
  events: [event()],
  incidents: [],
  ...overrides,
})
