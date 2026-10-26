import type { Dashboard, DashboardAlert, DashboardWindow } from '@/api/dashboard'

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
      highest: null,
      by_severity: {
        info: none(buckets),
        low: none(buckets),
        medium: none(buckets),
        high: none(buckets),
        critical: none(buckets),
      },
    },
    recent_alerts: [],
    blocked: { total: 0, previous: 0, per_bucket: none(buckets), top_sources: [] },
    traffic: [],
    devices: { total: 0, new: 0 },
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
