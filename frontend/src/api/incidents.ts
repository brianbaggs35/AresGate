import { apiGet, apiPatch } from '@/api/client'
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
  /** How many incidents there are in each status, whatever the search was for. */
  counts: Record<IncidentStatus, number>
}

/** What to look for. Nothing given matches everything. */
export interface IncidentQuery {
  statuses?: readonly IncidentStatus[]
  minSeverity?: Severity
  minConfidence?: number
  address?: string
  limit?: number
  offset?: number
}

/** The incidents that match, the ones going most recently first. */
export function fetchIncidents(query: IncidentQuery = {}): Promise<IncidentPage> {
  const params = new URLSearchParams()
  for (const status of query.statuses ?? []) params.append('status', status)
  if (query.minSeverity) params.set('min_severity', query.minSeverity)
  if (query.minConfidence) params.set('min_confidence', query.minConfidence.toString())
  if (query.address) params.set('address', query.address)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
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
