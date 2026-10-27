import { apiDelete, apiGet, apiPatch, apiPost } from '@/api/client'

/** What can be said of a signal: the first two keep it from ever raising an alarm, and the last
 * says it is real whatever AresGate made of it. */
export const VERDICTS = ['not_suspicious', 'low_priority', 'threat'] as const
export type VerdictKind = (typeof VERDICTS)[number]

/** What the owner said of the signals that match, remembered so that it holds from then on. */
export interface Verdict {
  id: number
  verdict: VerdictKind
  /** What it is about: a signal has to match all that are set, and at least one is. */
  address: string | null
  /** An integration's key, and its name. */
  source: string | null
  source_name: string | null
  signature: string | null
  note: string | null
  created_at: string
  updated_at: string
  /** How many signals in incidents it has been applied to, and when the latest happened. */
  hits: number
  last_hit_at: string | null
}

/** A verdict as it was just given: `replaced` is what it said before when saying it changed a
 * verdict that was already there, and null when it is a new one. */
export interface VerdictGiven extends Verdict {
  replaced: VerdictKind | null
}

/** A verdict to give: what it says and what it is about. */
export interface VerdictRequest {
  verdict: VerdictKind
  address?: string
  source?: string
  signature?: string
  note?: string
}

/** What can be changed of a verdict afterwards. A `null` note takes the note off. */
export interface VerdictChange {
  verdict?: VerdictKind
  note?: string | null
}

/** The verdicts, the one given last first. */
export async function fetchVerdicts(): Promise<Verdict[]> {
  return (await apiGet<{ items: Verdict[] }>('/verdicts')).items
}

/** Says it. Saying it again of the same thing changes the verdict that was there. */
export function giveVerdict(request: VerdictRequest, csrfToken: string): Promise<VerdictGiven> {
  return apiPost<VerdictGiven>('/verdicts', request, csrfToken)
}

export function changeVerdict(
  id: number,
  change: VerdictChange,
  csrfToken: string,
): Promise<Verdict> {
  return apiPatch<Verdict>(`/verdicts/${id.toString()}`, change, csrfToken)
}

/** Takes a verdict back: what it matched is judged as if it had never been said. */
export function removeVerdict(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/verdicts/${id.toString()}`, csrfToken)
}
