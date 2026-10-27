import { apiGet, apiPatch } from '@/api/client'
import type { VerdictKind } from '@/api/verdicts'
import type { Severity } from '@/severity'

/** What is being done about an incident. */
export const INCIDENT_STATUSES = ['open', 'investigating', 'resolved', 'dismissed'] as const
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number]

/** How sure AresGate is, in a word. */
export type ConfidenceLevel = 'low' | 'medium' | 'high'

/** An integration that reported part of an incident, by its key and by its name. */
export interface Program {
  key: string
  name: string
}

export interface Incident {
  id: number
  title: string
  /** The address the signals are about, or `rule:<integration>:<rule>` where they name none. */
  subject: string
  severity: Severity
  /** How sure AresGate is that it is a real attack, 0 to 100, and in a word. */
  confidence: number
  confidence_level: ConfidenceLevel
  status: IncidentStatus
  first_seen_at: string
  last_seen_at: string
  /** How many signals it has, which can be more than its timeline lists. */
  signal_count: number
  sources: Program[]
  /** Every address in the signals, the subject first. */
  addresses: string[]
  /** Whether an integration banned the address. */
  banned: boolean
  status_changed_at: string | null
  /** What the owner's verdicts say of it as a whole: a real threat, not suspicious or low
   * priority (because every signal is), or nothing. */
  verdict: VerdictKind | null
  /** How many of its signals each verdict was given of. The ones called not suspicious or low
   * priority are listed and counted in `signal_count`, but leave everything else about the
   * incident to the signals that are not. */
  verdict_counts: Partial<Record<VerdictKind, number>>
}

/** One thing that makes AresGate as sure as it is: the points add up to the confidence. */
export interface Reason {
  rule: string
  points: number
  text: string
}

export interface Signal {
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
  /** What the owner's verdicts said of it, and the verdict that said it while that exists. */
  verdict: VerdictKind | null
  verdict_rule_id: number | null
}

/** A device on the network that one of the incident's addresses belongs to. */
export interface IncidentDevice {
  id: number
  address: string
  mac: string
  hostname: string | null
  vendor: string | null
}

export interface IncidentDetail extends Incident {
  reasons: Reason[]
  /** Oldest first. Only the first so many are kept: `signal_count` has them all. */
  signals: Signal[]
  devices: IncidentDevice[]
  /** How many times the firewall turned the subject away around then, or null for an incident
   * about a rule rather than an address. */
  blocked: number | null
}

export interface IncidentPage {
  total: number
  items: Incident[]
  /** How many incidents there are in each status, whatever the search was for except which
   * verdicts it asked about. */
  counts: Record<IncidentStatus, number>
  /** How many more it would have found if it had not left out the ones the owner called not
   * suspicious or low priority. */
  quieted: number
}

/** What to look for. Nothing given matches everything. */
export interface IncidentQuery {
  statuses?: readonly IncidentStatus[]
  /** Only those the owner gave this verdict of, `none` being those they gave none of. */
  verdicts?: readonly (VerdictKind | 'none')[]
  minSeverity?: Severity
  minConfidence?: number
  address?: string
  limit?: number
  offset?: number
  /** `priority` puts the most serious and surest first; the default is the most recent. */
  order?: 'recent' | 'priority'
}

/** The incidents that match, the ones going most recently first unless asked for the most serious. */
export function fetchIncidents(query: IncidentQuery = {}): Promise<IncidentPage> {
  const params = new URLSearchParams()
  for (const status of query.statuses ?? []) params.append('status', status)
  for (const verdict of query.verdicts ?? []) params.append('verdict', verdict)
  if (query.minSeverity) params.set('min_severity', query.minSeverity)
  if (query.minConfidence) params.set('min_confidence', query.minConfidence.toString())
  if (query.address) params.set('address', query.address)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  if (query.order) params.set('order', query.order)
  const search = params.toString()
  return apiGet<IncidentPage>(search ? `/incidents?${search}` : '/incidents')
}

/** One incident with the reasons for its confidence, its timeline and the devices in it. */
export function fetchIncident(id: number): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/incidents/${id.toString()}`)
}

/** Says what is being done about an incident, and returns it as it is now. */
export function setIncidentStatus(
  id: number,
  status: IncidentStatus,
  csrfToken: string,
): Promise<IncidentDetail> {
  return apiPatch<IncidentDetail>(`/incidents/${id.toString()}`, { status }, csrfToken)
}
