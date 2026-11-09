import type {
  AssetAddress,
  AssetDetail,
  AssetEvent,
  AssetIncident,
  AssetPeer,
  AssetReading,
  AssetTraffic,
  AssetVerdict,
} from '@/api/assets'
import { asset } from '@/test/assets'

/** An asset's page as the API describes it, for tests of pages that show one. */

export const address = (overrides: Partial<AssetAddress> = {}): AssetAddress => ({
  address: '192.168.1.20',
  current: true,
  first_seen_at: '2026-09-01T10:00:00Z',
  last_seen_at: '2026-11-01T11:58:00Z',
  ...overrides,
})

/** An event its address was in: the laptop sent a blocked connection to a server on the internet. */
export const event = (overrides: Partial<AssetEvent> = {}): AssetEvent => ({
  id: 1,
  occurred_at: '2026-11-01T11:50:00Z',
  source: 'opnsense',
  source_name: 'OPNsense',
  kind: 'firewall',
  severity: 'info',
  summary: 'Blocked tcp',
  signature: null,
  src_address: '192.168.1.20',
  src_port: 51514,
  dst_address: '52.1.2.3',
  dst_port: 443,
  protocol: 'tcp',
  outbound: true,
  ...overrides,
})

export const peer = (overrides: Partial<AssetPeer> = {}): AssetPeer => ({
  address: '52.1.2.3',
  events: 3,
  last_seen_at: '2026-11-01T11:50:00Z',
  ...overrides,
})

/** What was measured in one stretch of time. Nothing is null where nothing was measured. */
export const reading = (overrides: Partial<AssetReading> = {}): AssetReading => ({
  at: '2026-11-01T11:00:00Z',
  sent: null,
  received: null,
  ...overrides,
})

export const traffic = (overrides: Partial<AssetTraffic> = {}): AssetTraffic => ({
  measured: false,
  hours: [],
  days: [],
  sent_day: 0,
  received_day: 0,
  sent_week: 0,
  received_week: 0,
  ...overrides,
})

export const incident = (overrides: Partial<AssetIncident> = {}): AssetIncident => ({
  id: 7,
  title: 'Repeated sign-in failures',
  severity: 'high',
  confidence: 80,
  status: 'open',
  verdict: null,
  last_seen_at: '2026-11-01T11:40:00Z',
  signal_count: 12,
  sources: ['wazuh'],
  ...overrides,
})

export const verdict = (overrides: Partial<AssetVerdict> = {}): AssetVerdict => ({
  id: 3,
  verdict: 'not_suspicious',
  address: '192.168.1.20',
  destination: null,
  source: null,
  signature: null,
  note: null,
  created_at: '2026-10-30T09:00:00Z',
  ...overrides,
})

/** An asset's page: a laptop on the home network with nothing else to show. */
export const detail = (overrides: Partial<AssetDetail> = {}): AssetDetail => ({
  asset: asset(),
  networks: [{ id: 4, name: 'Home' }],
  addresses: [address()],
  events: [],
  events_day: 0,
  events_week: 0,
  talks_to: [],
  contacted_by: [],
  traffic: traffic(),
  incidents: [],
  verdicts: [],
  ...overrides,
})
