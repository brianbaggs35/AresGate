import { apiGet, apiPost, apiPut } from '@/api/client'
import type { DashboardWindow, WindowInfo } from '@/api/dashboard'
import type { FamilyBrief, Incident, Lane, OwnerCall } from '@/api/incidents'
import type { Severity } from '@/severity'

/** Whether an AI has judged a kind of incident, you have called it, or neither yet. */
export const JUDGED = ['ai', 'owner', 'waiting'] as const
export type Judged = (typeof JUDGED)[number]

/** From what programs reported to what needs a person, in the order they are narrowed down. */
export interface Funnel {
  /** Every time a program reported an alert. */
  reports: number
  /** Reports of something another program had already reported. */
  duplicates: number
  /** Reports of something that had just been reported again by the same program. */
  repeats: number
  /** What is left: each alert counted once. */
  alerts: number
  incidents: number
  families: number
  threats: number
  suspects: number
  background: number
  muted: number
  handled: number
}

/** How many of the kinds of incident that are going on have been judged. */
export interface Coverage {
  families: number
  judged: number
  owned: number
  waiting: number
}

/** A kind of incident and what the incidents of it that are going on come to. */
export interface Family extends FamilyBrief {
  alerts: number
  /** How many different addresses (or rules) they are about. */
  actors: number
  worst: Severity
  first_seen_at: string
  last_seen_at: string
  threats: number
  suspects: number
  background: number
}

export interface Overview {
  window: WindowInfo
  funnel: Funnel
  coverage: Coverage
  /** Whether an AI is watching, which is when its agreement is needed for a threat. */
  watching: boolean
  threat_from: number
  families: Family[]
}

export interface FamilyPage {
  total: number
  items: Family[]
}

export interface FamilyDetail extends Family {
  provider: string | null
  model: string | null
  owner_call_at: string | null
  /** What is behind the call on the kind, a fact to a line. */
  why: string[]
  /** The incidents of it going on, the most recent first. */
  sample: Incident[]
}

/** What came of asking the AI about a kind: when it could not be asked, `reason` says why. */
export interface Judgement {
  ok: boolean
  reason: string | null
  family: FamilyDetail
}

export interface FamilyQuery {
  lane?: Lane
  judged?: Judged
  q?: string
  limit?: number
  offset?: number
}

export function fetchOverview(window: DashboardWindow): Promise<Overview> {
  return apiGet<Overview>(`/threats/overview?window=${window}`)
}

export function fetchFamilies(query: FamilyQuery = {}): Promise<FamilyPage> {
  const params = new URLSearchParams()
  if (query.lane) params.set('lane', query.lane)
  if (query.judged) params.set('judged', query.judged)
  if (query.q) params.set('q', query.q)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const text = params.toString()
  return apiGet<FamilyPage>(text ? `/threats/families?${text}` : '/threats/families')
}

export function fetchFamily(id: number): Promise<FamilyDetail> {
  return apiGet<FamilyDetail>(`/threats/families/${id}`)
}

/** Says what is to be done with a whole kind of incident, or takes your word back (null). */
export function callFamily(
  id: number,
  call: OwnerCall | null,
  csrfToken: string,
): Promise<FamilyDetail> {
  return apiPut<FamilyDetail>(`/threats/families/${id}/call`, { call }, csrfToken)
}

/** Asks the AI what a kind of incident is. */
export function judgeFamily(id: number, csrfToken: string): Promise<Judgement> {
  return apiPost<Judgement>(`/threats/families/${id}/judge`, {}, csrfToken)
}
