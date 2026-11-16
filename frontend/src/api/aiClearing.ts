import { apiGet, apiPost, apiPut } from '@/api/client'

/** Off (it clears nothing), suggest (it marks what looks like a false positive and waits for a
 * tap), or automatic (it gives the verdict, which can be taken back). */
export const CLEARING_MODES = ['off', 'suggest', 'automatic'] as const
export type ClearingMode = (typeof CLEARING_MODES)[number]

/** The kinds of reading it may clear. An attack or a compromise never is. */
export const CLEARING_KINDS = ['noise', 'probe', 'unclear'] as const
export type ClearingKind = (typeof CLEARING_KINDS)[number]

/** The most serious an incident can be and still be cleared. Critical never is. */
export const CLEARING_CEILINGS = ['low', 'medium', 'high'] as const
export type ClearingCeiling = (typeof CLEARING_CEILINGS)[number]

/** What is changed when saving, which is all of it. */
export interface ClearingDraft {
  mode: ClearingMode
  /** How sure the AI has to be, as it says so itself, from 50 to 99. */
  minimum: number
  kinds: ClearingKind[]
  /** The programs whose incidents it may clear; none named is any program. */
  sources: string[]
  ceiling: ClearingCeiling
  /** The most it clears by itself in 24 hours. */
  daily_cap: number
}

/** One way of being careful: how sure the AI must be, and what that comes to. */
export interface ClearingPreset {
  key: 'careful' | 'balanced' | 'thorough'
  minimum: number
  summary: string
}

export interface ClearingSource {
  key: string
  name: string
}

export interface Clearing extends ClearingDraft {
  /** The preset that asks as much as `minimum`, or custom. */
  aggressiveness: ClearingPreset['key'] | 'custom'
  presets: ClearingPreset[]
  available_sources: ClearingSource[]
  min_minimum: number
  max_minimum: number
  max_cap: number
  /** How many verdicts it gave in the last 24 hours. */
  cleared_today: number
  /** Why it is not clearing by itself right now, in words, or null. */
  held: string | null
  updated_at: string | null
}

/** What the settings would have done in the last days. */
export interface ClearingPreview {
  days: number
  read: number
  would_clear: number
}

export function fetchClearing(): Promise<Clearing> {
  return apiGet<Clearing>('/ai/clearing')
}

export function saveClearing(draft: ClearingDraft, csrfToken: string): Promise<Clearing> {
  return apiPut<Clearing>('/ai/clearing', draft, csrfToken)
}

/** How many of the incidents the AI read lately the settings would have cleared. Nothing is kept. */
export function previewClearing(draft: ClearingDraft, csrfToken: string): Promise<ClearingPreview> {
  return apiPost<ClearingPreview>('/ai/clearing/preview', draft, csrfToken)
}
