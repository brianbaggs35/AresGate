import { apiGet, apiPatch, apiPost } from '@/api/client'
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

/** What kind of activity its signals say it was: a scan of ports, or guessing at logins. */
export type Activity = 'scan' | 'brute_force'

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
  /** What its signals say it was, where they say. */
  activities: Activity[]
  /** How many bursts they came in, with a quarter of an hour of quiet between them: a bot that
   * sweeps the network three times in an afternoon is one incident with three waves. */
  waves: number
  /** How many different destination ports they touched, as far as are kept (`ports_capped`). */
  port_count: number
  ports_capped: boolean
  /** How many other addresses of the subject's block (a /24 or /64) are grouped into it. */
  neighbours: number
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
  /** Why its signals are one incident, in plain words, a fact to a line. */
  grouping: string[]
  /** The destination ports they touched, lowest first. */
  ports: number[]
  /** Oldest first. Only the first so many are kept: `signal_count` has them all. */
  signals: Signal[]
  devices: IncidentDevice[]
  /** How many times the firewall turned the subject away around then, or null for an incident
   * about a rule rather than an address. */
  blocked: number | null
}

/** One term of a search as AresGate understood it: what it is about and how to read it back. */
export interface SearchTerm {
  /** `source`, `severity` and the like, or null for plain words. */
  field: string | null
  /** In words to show: `Source: Wazuh`, `Not address: 10.0.0.0/8`. */
  label: string
  negated: boolean
  /** Where it was in the text of the search: the characters from `start` up to `end`. */
  start: number
  end: number
}

/** An integration and how many of the incidents found it reported part of. */
export interface SourceCount {
  key: string
  name: string
  count: number
}

/** How the incidents found are spread, whatever page of them is on screen. */
export interface Facets {
  severity: Record<Severity, number>
  /** The most first. */
  sources: SourceCount[]
}

export interface IncidentPage {
  total: number
  items: Incident[]
  /** The search in words, as it was understood: one for each term. */
  terms: SearchTerm[]
  facets: Facets
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
  /** A search in words, such as `severity>=high source:wazuh -port:22`. */
  q?: string
  /** The time zone the person is in, for what `today` means in a search. */
  tz?: string
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
  if (query.q) params.set('q', query.q)
  if (query.tz) params.set('tz', query.tz)
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

/** Which incidents a change is for: the ones that were picked, or all that a list of incidents
 * asked this way would show. */
export type BulkSelection = { ids: readonly number[] } | { matching: IncidentQuery }

/** What to change in all of them: what is being done about them, or what is thought of what they
 * are about (with a note, to say why). */
export type BulkChange = { status: IncidentStatus } | { verdict: VerdictKind; note?: string }

/** How to take a change back, as the change said it. */
export interface BulkUndo {
  /** The incidents it changed, by the status they had. */
  statuses: Partial<Record<IncidentStatus, number[]>>
  /** The verdicts it made, and what each said before (null if it is new). */
  rules: { id: number; replaced: VerdictKind | null }[]
}

/** What a change did, or with `preview` what it would do. */
export interface BulkResult {
  preview: boolean
  /** How many incidents it was about, and how many signals are in them. */
  incidents: number
  signals: number
  /** In how many of them it changes anything: the others already are so. */
  changed: number
  /** For a verdict, the incidents it could not be given on (no address and no alert), and how
   * many verdicts it makes or changes: one covers every incident about an address or alert. */
  skipped: number
  verdicts: number
  /** Null where nothing was changed, or where it was only asked about. */
  undo: BulkUndo | null
}

function matchingOf(query: IncidentQuery) {
  return {
    status: query.statuses ?? [],
    verdict: query.verdicts ?? [],
    ...(query.minSeverity ? { min_severity: query.minSeverity } : {}),
    min_confidence: query.minConfidence ?? 0,
    ...(query.address ? { address: query.address } : {}),
    ...(query.q ? { q: query.q } : {}),
    ...(query.tz ? { tz: query.tz } : {}),
  }
}

/** Changes many incidents in one go, all or none. With `preview` it only says what it would do. */
export function changeIncidents(
  selection: BulkSelection,
  change: BulkChange,
  csrfToken: string,
  preview = false,
): Promise<BulkResult> {
  const which =
    'ids' in selection ? { ids: selection.ids } : { matching: matchingOf(selection.matching) }
  return apiPost<BulkResult>(
    '/incidents/bulk',
    { ...which, ...change, ...(preview ? { preview } : {}) },
    csrfToken,
  )
}

/** Takes a change back, as it said how: how many incidents and verdicts that put right. */
export function undoChange(
  undo: BulkUndo,
  csrfToken: string,
): Promise<{ incidents: number; verdicts: number }> {
  return apiPost('/incidents/bulk/undo', undo, csrfToken)
}
