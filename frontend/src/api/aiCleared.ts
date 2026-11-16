import { apiGet, apiPost } from '@/api/client'
import type { Severity } from '@/severity'

/** What the AI cleared (`cleared`: a verdict it gave itself) or suggests clearing (`waiting`). */
export type ClearedState = 'waiting' | 'cleared'

/** What the AI says an incident is: nothing to worry about, or not worth hearing about. */
export type ClearedVerdict = 'not_suspicious' | 'low_priority'

/** How many are in each list. */
export interface ClearedCounts {
  waiting: number
  cleared: number
}

/** The incident an item is about. */
export interface ClearedIncident {
  id: number
  title: string
  severity: Severity
  status: string
  subject: string
  last_seen_at: string
}

/** One suggestion or one verdict the AI gave, with why and what it read. */
export interface ClearedItem {
  kind: ClearedState
  /** The verdict's id for one that is cleared, the incident's for one that waits. */
  id: number
  /** Null where the incident is gone. */
  incident: ClearedIncident | null
  verdict: ClearedVerdict
  reason: string | null
  confidence: number | null
  classification: string | null
  provider: string | null
  model: string | null
  /** When it was cleared, or when the AI read what it suggests clearing. */
  at: string
  story: string | null
  checks: string[]
  observations: string[]
}

export interface ClearedPage {
  state: ClearedState
  counts: ClearedCounts
  total: number
  items: ClearedItem[]
  mode: 'off' | 'suggest' | 'automatic'
  /** Why it is not clearing by itself right now, if so. */
  held: string | null
}

/** Which items to do something to. */
export interface ClearedPick {
  kind: ClearedState
  id: number
}

/** How many were done, and how many were no longer there. */
export interface ClearedChanged {
  done: number
  skipped: number
  counts: ClearedCounts
}

export function fetchCleared(state: ClearedState, limit = 20, offset = 0): Promise<ClearedPage> {
  return apiGet<ClearedPage>(
    `/ai/cleared?state=${state}&limit=${limit.toString()}&offset=${offset.toString()}`,
  )
}

export function fetchClearedCounts(): Promise<ClearedCounts> {
  return apiGet<ClearedCounts>('/ai/cleared/summary')
}

/** Makes what the AI cleared the owner's, and gives what it suggests as the owner's verdict (as
 * `verdict`, if that is another than the AI's). */
export function confirmCleared(
  items: readonly ClearedPick[],
  csrfToken: string,
  verdict?: ClearedVerdict,
): Promise<ClearedChanged> {
  return apiPost<ClearedChanged>('/ai/cleared/confirm', { items, verdict }, csrfToken)
}

/** Takes back what the AI cleared, and turns down what it suggests. */
export function takeBackCleared(
  items: readonly ClearedPick[],
  csrfToken: string,
): Promise<ClearedChanged> {
  return apiPost<ClearedChanged>('/ai/cleared/take-back', { items }, csrfToken)
}
