import type {
  Attention,
  Dashboard,
  DashboardAlert,
  DashboardWindow,
  IncidentMark,
  NoisySignature,
  SourceAlerts,
} from '@/api/dashboard'

const HOUR = 3_600_000
const END = Date.parse('2026-10-26T19:00:00Z')
const LENGTHS = { '24h': [24, 24, 96], '7d': [168, 28, 168] } as const

/** Each of the starts of `count` equal buckets that end at the window's end. */
const starts = (end: number, hours: number, count: number) =>
  Array.from({ length: count }, (_, index) =>
    new Date(end - hours * HOUR + (index * hours * HOUR) / count).toISOString(),
  )

const none = (count: number) => new Array<number>(count).fill(0)

/** A dashboard for a network where nothing happened, with whatever is given changed. The counts
 * are by hour for a day and by six hours for a week, and the traffic by quarter hour or hour.
 * The window ends at `end` (milliseconds since 1970), which is a fixed time unless given. */
export function dashboard(
  changes: Partial<Dashboard> = {},
  key: DashboardWindow = '24h',
  end = END,
): Dashboard {
  const [hours, buckets, trafficBuckets] = LENGTHS[key]
  return {
    window: {
      key,
      start: new Date(end - hours * HOUR).toISOString(),
      end: new Date(end).toISOString(),
      buckets: starts(end, hours, buckets),
      traffic_buckets: starts(end, hours, trafficBuckets),
    },
    alerts: {
      total: 0,
      previous: 0,
      reports: 0,
      duplicates: 0,
      highest: null,
      by_severity: {
        info: none(buckets),
        low: none(buckets),
        medium: none(buckets),
        high: none(buckets),
        critical: none(buckets),
      },
    },
    attention: attention(),
    noise: { sources: [], signatures: [] },
    recent_alerts: [],
    blocked: {
      total: 0,
      previous: 0,
      per_bucket: none(buckets),
      top_sources: [],
      inbound: 0,
      outbound: 0,
      inside: 0,
      top_ports: [],
      top_devices: [],
    },
    traffic: [],
    devices: { total: 0, new: 0 },
    marks: [],
    ...changes,
  }
}

export function alert(changes: Partial<DashboardAlert> = {}): DashboardAlert {
  return {
    id: 1,
    occurred_at: new Date(END - 5 * 60_000).toISOString(),
    source: 'wazuh',
    source_name: 'Wazuh',
    severity: 'medium',
    summary: 'sshd: authentication failed',
    signature: '5710',
    src_address: '198.51.100.20',
    dst_address: '192.168.1.20',
    ...changes,
  }
}

/** An incident of the dashboard's window, from a quarter past two in the afternoon of the day
 * before it ends, unless it says otherwise. */
export function incidentMark(changes: Partial<IncidentMark> = {}): IncidentMark {
  return {
    id: 1,
    title: 'Brute force on ssh (93.184.216.34)',
    subject: '93.184.216.34',
    severity: 'high',
    confidence: 70,
    status: 'open',
    first_seen_at: '2026-10-26T14:15:00Z',
    last_seen_at: '2026-10-26T14:40:00Z',
    banned: false,
    ...changes,
  }
}

/** What one program reported as alerts: 120, 80 of them serious, and none between two addresses
 * on the network, unless it says otherwise. */
export function sourceAlerts(changes: Partial<SourceAlerts> = {}): SourceAlerts {
  return {
    source: 'ntopng',
    source_name: 'ntopng',
    total: 120,
    serious: 80,
    inside: 0,
    ...changes,
  }
}

/** An alert that ntopng reported 120 times in the window from 3 addresses to 9, and nobody has
 * said anything of. */
export function noisySignature(changes: Partial<NoisySignature> = {}): NoisySignature {
  return {
    source: 'ntopng',
    source_name: 'ntopng',
    signature: 'Blacklisted flow',
    severity: 'high',
    count: 120,
    from_addresses: 3,
    to_addresses: 9,
    first_at: new Date(END - 20 * HOUR).toISOString(),
    last_at: new Date(END - 5 * 60_000).toISOString(),
    verdict: null,
    verdict_rule_id: null,
    ...changes,
  }
}

/** The incidents of a window when none were going on, with whatever is given changed. */
export function attention(changes: Partial<Attention> = {}): Attention {
  return {
    incidents: 0,
    floor: 35,
    handled: 0,
    muted: 0,
    unsure: 0,
    cleared: 0,
    needs_you: 0,
    urgent: 0,
    ...changes,
  }
}
