import { apiGet, apiPost, apiPut } from '@/api/client'
import type { Classification, ReviewState } from '@/api/incidents'
import type { Severity } from '@/severity'

export type { ReviewState }

/** What a decision is about: one incident the AI read, or a kind of incident it judged. */
export type DecisionSubject = 'incident' | 'family'

/** The three lists of the page. */
export type ReviewList = 'waiting' | 'decided' | 'answered'

/** One thing the AI decided. */
export interface Decision {
  subject: DecisionSubject
  id: number
  review: ReviewState
  kind: Classification
  confidence: number
  title: string
  /** The AI's reason, in its words. */
  why: string
  suggestion: 'not_suspicious' | 'low_priority' | 'threat' | null
  decided_at: string
  reviewed_at: string | null
  /** How many incidents it is about, and how many of them are going on. */
  incidents: number
  active: number
  severity: Severity | null
  provider: string | null
  model: string | null
  /** What the owner said of it, if they gave a reason. */
  reason: string | null
  /** Whether it counts now: a decision that waits counts only if it raises the alarm. */
  counting: boolean
  /** What it does, in a line. */
  effect: string
}

export interface ReviewCounts {
  waiting: number
  decided: number
  answered: number
}

/** How often the owner has agreed with the AI, and whether that is enough to let it decide. */
export interface ReviewStanding {
  agreed: number
  disagreed: number
  rate: number | null
  trusted: boolean
  trust_after: number
  trust_rate: number
}

/** How much of what the AI decides waits for the owner: all of it, what it is unsure of, or none. */
export const REVIEW_MODES = ['all', 'uncertain', 'auto'] as const
export type ReviewMode = (typeof REVIEW_MODES)[number]

export interface ReviewPage {
  state: ReviewList
  total: number
  items: Decision[]
  counts: ReviewCounts
  standing: ReviewStanding
  mode: ReviewMode
}

export type Answer = 'agree' | 'disagree' | 'undo'

export interface ReviewDraft {
  mode: ReviewMode
  /** With `uncertain`: how sure the AI has to be for a decision to count at once. */
  auto_from: number
  /** Whether what the owner disagreed with, and why, goes to the AI the next time it decides. */
  learn: boolean
}

export interface ReviewSettings extends ReviewDraft {
  default_mode: ReviewMode
  default_auto_from: number
  min_auto_from: number
  updated_at: string | null
}

/** The decisions in one list, with how many there are in each. */
export function fetchReview(list: ReviewList, limit: number, offset = 0): Promise<ReviewPage> {
  const params = new URLSearchParams({ state: list, limit: limit.toString() })
  if (offset) params.set('offset', offset.toString())
  return apiGet<ReviewPage>(`/review?${params.toString()}`)
}

/** How many decisions wait for the owner. */
export function fetchWaiting(): Promise<{ waiting: number }> {
  return apiGet<{ waiting: number }>('/review/summary')
}

/** Says that the owner agrees or disagrees with a decision, or takes the answer back. */
export function answerDecision(
  subject: DecisionSubject,
  id: number,
  answer: Answer,
  reason: string | null,
  keepKind: boolean,
  csrfToken: string,
): Promise<Decision> {
  return apiPost<Decision>(
    `/review/${subject}/${id.toString()}`,
    { answer, reason, keep_kind: keepKind },
    csrfToken,
  )
}

/** Agrees with each decision given that is still waiting. */
export function agreeWith(
  items: readonly { subject: DecisionSubject; id: number }[],
  csrfToken: string,
): Promise<{ agreed: number }> {
  return apiPost<{ agreed: number }>('/review/agree', { items }, csrfToken)
}

export function fetchReviewSettings(): Promise<ReviewSettings> {
  return apiGet<ReviewSettings>('/review/settings')
}

export function saveReviewSettings(draft: ReviewDraft, csrfToken: string): Promise<ReviewSettings> {
  return apiPut<ReviewSettings>('/review/settings', draft, csrfToken)
}
