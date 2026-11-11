import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'
import type { IncidentStatus } from '@/api/incidents'
import type { Severity } from '@/severity'

/** How much to trust something: `not_suspicious` is safe, `low_priority` is only worth a glance. */
export type TrustLevel = 'not_suspicious' | 'low_priority'

/** What the owner said is safe: it keeps what it matches from raising an alarm, for every program
 * AresGate reads. */
export interface Trust {
  id: number
  verdict: TrustLevel
  /** What it is about, in a sentence. */
  about: string
  /** At least one of these is set, and a signal has to match all that are. */
  address: string | null
  /** Where that address sends its traffic: only with an address. */
  destination: string | null
  source: string | null
  source_name: string | null
  signature: string | null
  note: string | null
  created_at: string
  updated_at: string
  /** How many signals it has kept from raising an alarm, in how many incidents, and when last. */
  hits: number
  incidents: number
  last_hit_at: string | null
}

export interface TrustList {
  items: Trust[]
  safe: number
  low_priority: number
  /** How many signals, in all, a decision has kept from raising an alarm. */
  applied: number
}

/** An incident a decision was applied to. */
export interface AppliedIncident {
  id: number
  title: string
  severity: Severity
  status: IncidentStatus
  last_seen_at: string
  signals: number
}

export interface TrustDetail extends Trust {
  applied_to: AppliedIncident[]
}

/** An incident the AI read and thinks is nothing to worry about, that nothing trusts yet. */
export interface Suggestion {
  incident_id: number
  title: string
  subject: string
  severity: Severity
  last_seen_at: string
  verdict: TrustLevel
  confidence: number
  headline: string
  reason: string | null
}

/** What to trust: the same as what a decision is about, and how much. */
export interface TrustRequest {
  verdict?: TrustLevel
  address?: string
  destination?: string
  source?: string
  signature?: string
  note?: string
}

export function fetchTrust(): Promise<TrustList> {
  return apiGet<TrustList>('/trust')
}

export async function fetchSuggestions(): Promise<Suggestion[]> {
  return (await apiGet<{ items: Suggestion[] }>('/trust/suggestions')).items
}

export function fetchTrusted(id: number): Promise<TrustDetail> {
  return apiGet<TrustDetail>(`/trust/${id.toString()}`)
}

/** Trusts it, at once, for what is going on and from here on. */
export function trust(request: TrustRequest, csrfToken: string): Promise<Trust> {
  return apiPost<Trust>('/trust', request, csrfToken)
}

/** Changes everything about a decision. */
export function changeTrust(id: number, request: TrustRequest, csrfToken: string): Promise<Trust> {
  return apiPut<Trust>(`/trust/${id.toString()}`, request, csrfToken)
}

/** Takes a decision back: what it covered is judged as if it had never been said. */
export function revokeTrust(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/trust/${id.toString()}`, csrfToken)
}
