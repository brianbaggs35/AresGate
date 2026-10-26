import { apiGet } from '@/api/client'
import type { Severity } from '@/severity'

/** How far back the dashboard looks. */
export type DashboardWindow = '24h' | '7d'

/** The windows people can pick, shortest first, with what each is called and what comes before
 * it ("the day before"). */
export const WINDOWS: readonly { key: DashboardWindow; label: string; before: string }[] = [
  { key: '24h', label: '24 hours', before: 'the day before' },
  { key: '7d', label: '7 days', before: 'the week before' },
]

export interface WindowInfo {
  key: DashboardWindow
  start: string
  end: string
  /** When each bucket of the counts starts, and each bucket of the traffic. */
  buckets: string[]
  traffic_buckets: string[]
}

/** How many there were in the window and in the one before it, and in each bucket. */
export interface Counted {
  total: number
  previous: number
  per_bucket: number[]
}

export interface AlertCounts {
  total: number
  previous: number
  /** The most serious alert there was, or null when there were none. */
  highest: Severity | null
  /** For every severity, how many in each bucket. */
  by_severity: Record<Severity, number[]>
}

export interface DashboardAlert {
  id: number
  occurred_at: string
  /** The integration that reported it, such as `wazuh`, and what it is called. */
  source: string
  source_name: string
  severity: Severity
  summary: string
  signature: string | null
  src_address: string | null
  dst_address: string | null
}

export interface BlockedSource {
  address: string
  count: number
}

export interface BlockedCounts extends Counted {
  top_sources: BlockedSource[]
}

/** How fast one interface went in each bucket, in bits a second; null where it can't be told. */
export interface InterfaceTraffic {
  interface: string
  received: (number | null)[]
  sent: (number | null)[]
}

export interface Dashboard {
  window: WindowInfo
  alerts: AlertCounts
  recent_alerts: DashboardAlert[]
  blocked: BlockedCounts
  traffic: InterfaceTraffic[]
  devices: { total: number; new: number }
}

export function fetchDashboard(window: DashboardWindow): Promise<Dashboard> {
  return apiGet<Dashboard>(`/dashboard?window=${window}`)
}
