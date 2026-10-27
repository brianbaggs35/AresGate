import { apiGet } from '@/api/client'
import type { IncidentStatus, SearchTerm, SourceCount } from '@/api/incidents'
import type { Severity } from '@/severity'

/** An event as the list shows it: what an integration reported, in AresGate's own words. */
export interface LogEvent {
  /** Where it is in the order of the logs, which finds it again. */
  cursor: string
  id: number
  /** When it happened, by the clock of whatever reported it. */
  at: string
  /** When AresGate heard of it. */
  received_at: string
  source: string
  source_name: string
  /** Which connection of the integration brought it. */
  connection: string
  kind: string
  severity: Severity
  summary: string
  /** The rule that fired, for an alert. */
  signature: string | null
  src_address: string | null
  src_port: number | null
  dst_address: string | null
  dst_port: number | null
  protocol: string | null
  /** Whether the integration's own record was kept, which the detail has. */
  has_raw: boolean
}

/** The incident an event was filed into. */
export interface LogIncident {
  id: number
  title: string
  status: IncidentStatus
  severity: Severity
}

/** One event whole: with the integration's own record of it, as it was received. */
export interface LogDetail extends LogEvent {
  raw: Record<string, unknown> | null
  incident: LogIncident | null
}

export interface KindCount {
  kind: string
  count: number
}

/** How the events found are spread, whatever page of them is on screen. */
export interface LogFacets {
  severity: Record<Severity, number>
  /** The most first. */
  sources: SourceCount[]
  /** The most first. */
  kinds: KindCount[]
}

/** How many events there were in each stretch of time: `counts[bar][level]` is a count for each
 * severity from info to critical, and the first bar begins at `start`. */
export interface LogVolume {
  start: string
  seconds: number
  counts: number[][]
}

export interface LogSummary {
  /** How many events the spread is of: the newest that match, up to a limit. */
  matched: number
  /** Whether there were more, the oldest ones, that it did not read. */
  capped: boolean
  facets: LogFacets
  volume: LogVolume | null
}

export interface LogPage {
  items: LogEvent[]
  /** Whether there are more past the end of the page (older), or, for a page asked for after an
   * event, newer than it. */
  more: boolean
  /** The search in words, as it was understood: one for each term. */
  terms: SearchTerm[]
  /** Left out when it was not asked for. */
  summary: LogSummary | null
}

export interface LogQuery {
  /** A search in words, such as `severity>=high source:opnsense -port:22 since:1h`. */
  q?: string
  /** The time zone the person is in, for what `today` means in a search. */
  tz?: string
  limit?: number
  /** Only events older than this one (the `cursor` of the last on the page). */
  before?: string
  /** Only events newer than this one, the oldest first. */
  after?: string
  /** Whether to also say how the events found are spread. Once is enough. */
  summary?: boolean
}

/** The events that match, the newest first. */
export function fetchLogs(query: LogQuery = {}): Promise<LogPage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.tz) params.set('tz', query.tz)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.before) params.set('before', query.before)
  if (query.after) params.set('after', query.after)
  if (query.summary === false) params.set('summary', 'false')
  const search = params.toString()
  return apiGet<LogPage>(search ? `/logs?${search}` : '/logs')
}

/** One event whole, with the integration's own record of it. */
export function fetchLog(cursor: string): Promise<LogDetail> {
  return apiGet<LogDetail>(`/logs/${encodeURIComponent(cursor)}`)
}

export type LogFormat = 'csv' | 'json'

/** Where the events that a search finds can be downloaded as a file. It is a link, not a call:
 * the browser saves the file as it arrives, however long it is. */
export function exportAddress(format: LogFormat, query: Pick<LogQuery, 'q' | 'tz'> = {}): string {
  const params = new URLSearchParams({ format })
  if (query.q) params.set('q', query.q)
  if (query.tz) params.set('tz', query.tz)
  return `/api/logs/export?${params.toString()}`
}
