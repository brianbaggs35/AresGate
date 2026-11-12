import { apiGet } from '@/api/client'
import type { IncidentStatus } from '@/api/incidents'
import type { VerdictKind } from '@/api/verdicts'
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
  /** How many alerts there were, each counted once however often it was reported and by however
   * many programs. */
  total: number
  previous: number
  /** How many times programs reported alerts, and how many of those another program had
   * already reported. */
  reports: number
  duplicates: number
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

/** A port the internet tried and the firewall refused, and what it is usually for. */
export interface BlockedPort {
  port: number
  service: string | null
  count: number
}

/** One of your own devices that the firewall refused to let connect out. */
export interface BlockedDevice {
  address: string
  count: number
  /** How many different addresses it tried to reach. */
  destinations: number
}

export interface BlockedCounts extends Counted {
  top_sources: BlockedSource[]
  /** The same blocks by the way they were going: from the internet, out from one of your
   * devices, or between your own networks. */
  inbound: number
  outbound: number
  inside: number
  top_ports: BlockedPort[]
  top_devices: BlockedDevice[]
}

/** How fast one interface went in each bucket, in bits a second; null where it can't be told. */
export interface InterfaceTraffic {
  interface: string
  received: (number | null)[]
  sent: (number | null)[]
}

/** An incident that was going on in the window, for a flag on the charts. */
export interface IncidentMark {
  id: number
  title: string
  /** The address it is about, or `rule:<integration>:<rule>` where there is none. */
  subject: string
  severity: Severity
  confidence: number
  status: IncidentStatus
  first_seen_at: string
  last_seen_at: string
  banned: boolean
}

/** What one program reported as alerts in the window: how many, how many of them were high or
 * critical, and how many were between two addresses that are both on the network. */
export interface SourceAlerts {
  source: string
  source_name: string
  total: number
  serious: number
  inside: number
}

/** One alert (a rule, a signature) that a program reported often, and what the owner has said of
 * every alert like it. */
export interface NoisySignature {
  source: string
  source_name: string
  /** Null when the alerts do not say which rule raised them. */
  signature: string | null
  /** The most serious it was. */
  severity: Severity
  count: number
  from_addresses: number
  to_addresses: number
  first_at: string
  last_at: string
  /** What the owner said of every alert like it, whichever address it came from, and the rule
   * that says so: both null when they have said nothing. */
  verdict: VerdictKind | null
  verdict_rule_id: number | null
}

/** Where the alerts of the window come from: by program, and the ones reported most. */
export interface Noise {
  sources: SourceAlerts[]
  signatures: NoisySignature[]
}

/** What the incidents that were going on in the window come to for the owner: how many need
 * them, and why each of the others was filtered out. Every incident is in exactly one of the
 * five counts. */
export interface Attention {
  incidents: number
  /** The confidence an incident needs, at least, to be asked about. */
  floor: number
  /** Resolved or dismissed already. */
  handled: number
  /** Called not suspicious or low priority by a verdict. */
  muted: number
  /** AresGate's confidence in them is below the floor. */
  unsure: number
  /** Set aside by an AI that judged them background. */
  cleared: number
  /** The rest: they need the owner. */
  needs_you: number
  /** How many of those AresGate is highly confident of. */
  urgent: number
}

export interface Dashboard {
  window: WindowInfo
  alerts: AlertCounts
  attention: Attention
  noise: Noise
  recent_alerts: DashboardAlert[]
  blocked: BlockedCounts
  traffic: InterfaceTraffic[]
  devices: { total: number; new: number }
  /** The incidents to flag on the charts, in the order they began. */
  marks: IncidentMark[]
}

export function fetchDashboard(window: DashboardWindow): Promise<Dashboard> {
  return apiGet<Dashboard>(`/dashboard?window=${window}`)
}
