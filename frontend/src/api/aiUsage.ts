import { apiGet, apiPut } from '@/api/client'

/** The stretches of time the usage page can show. */
export type UsageRange = '7d' | '30d' | '90d'

/** What a set of calls added up to. Money is in millionths of a US dollar. */
export interface UsageTotals {
  calls: number
  failed: number
  input_tokens: number
  cached_tokens: number
  output_tokens: number
  /** What the calls with a known price cost. */
  cost_micros: number
  /** How many calls have no known price. */
  unpriced: number
}

/** What one use of AI took on each of the days, in the order of `days`. */
export interface UsageUse {
  purpose: string
  calls: number[]
  tokens: number[]
  cost_micros: number[]
}

/** Calls added up by something they share: the provider, the model or what they were for. */
export interface UsageGroup {
  key: string
  label: string
  /** The provider, for a model. */
  provider: string | null
  calls: number
  tokens: number
  cost_micros: number
  unpriced: number
}

/** Something the AI was asked about, such as an incident, and what that took. */
export interface UsageConsumer {
  about: string
  purpose: string
  calls: number
  tokens: number
  cost_micros: number
  /** The incident it was about, for a link. */
  incident_id: number | null
}

/** The calendar month (UTC, as providers bill it) so far. */
export interface UsageMonth {
  start: string
  end: string
  spent_micros: number
  unpriced: number
  /** At this pace, what the month will cost: none until there is a day to go on. */
  projected_micros: number | null
}

export type LimitState = 'none' | 'ok' | 'warning' | 'reached'

/** What may be spent in the last 24 hours (`day`) or in the month, and how much of it has gone. */
export interface UsageLimit {
  period: 'day' | 'month'
  limit_micros: number | null
  spent_micros: number
  state: LimitState
}

/** One of the levels of how much AI is used without being asked, from the least to the most. */
export interface UsageLevel {
  key: 'very_low' | 'low' | 'medium' | 'high' | 'maximum'
  label: string
  /** What it reads by itself, in words, made by the server from what the worker does. */
  summary: string
  /** The most it reads in an hour; none reads nothing by itself. */
  per_hour: number
}

export interface Usage {
  range: UsageRange
  start: string
  end: string
  /** When each day begins, in the time zone the page asked for. */
  days: string[]
  uses: UsageUse[]
  totals: UsageTotals
  /** The same for the stretch of time before. */
  previous: UsageTotals
  by_provider: UsageGroup[]
  by_model: UsageGroup[]
  by_purpose: UsageGroup[]
  top: UsageConsumer[]
  month: UsageMonth
  limits: UsageLimit[]
  /** The level chosen, and the levels there are to choose between. */
  level: UsageLevel['key']
  levels: UsageLevel[]
  /** Where the prices come from and when they were read. */
  prices: { as_of: string; sources: { provider: string; url: string }[] }
  /** Whether AI has ever been asked. */
  ever: boolean
}

/** One request to a provider, as it is recorded. */
export interface UsageCall {
  id: number
  occurred_at: string
  purpose: string
  about: string | null
  provider: string
  provider_label: string
  model: string
  model_label: string
  level: string
  ok: boolean
  input_tokens: number
  cached_tokens: number
  output_tokens: number
  cost_micros: number | null
  duration_ms: number
  truncated: boolean
  error: string | null
}

export interface UsageCallPage {
  total: number
  items: UsageCall[]
}

/** A call with what the provider was sent and what it answered, as it read them. */
export interface UsageCallDetail extends UsageCall {
  prompt: string
  answer: string | null
}

/** The time zone the person is in, which is what days are counted in. */
export function timeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

function query(range: UsageRange): string {
  return `range=${range}&timezone=${encodeURIComponent(timeZone())}`
}

export function fetchUsage(range: UsageRange): Promise<Usage> {
  return apiGet(`/ai/usage?${query(range)}`)
}

export function fetchUsageCalls(
  range: UsageRange,
  limit: number,
  offset: number,
): Promise<UsageCallPage> {
  return apiGet(
    `/ai/usage/calls?${query(range)}&limit=${limit.toString()}&offset=${offset.toString()}`,
  )
}

export function fetchUsageCall(id: number): Promise<UsageCallDetail> {
  return apiGet(`/ai/usage/calls/${id.toString()}`)
}

/** Where the calls in the range can be downloaded as a spreadsheet. */
export function usageCsvUrl(range: UsageRange): string {
  return `/api/ai/usage.csv?${query(range)}`
}

/** What may be spent, in dollars; none for no limit. */
export interface LimitsInput {
  daily: string | null
  monthly: string | null
}

export function saveLimits(limits: LimitsInput, csrfToken: string): Promise<UsageLimit[]> {
  return apiPut('/ai/limits', limits, csrfToken)
}

export function saveLevel(
  level: UsageLevel['key'],
  csrfToken: string,
): Promise<{ level: UsageLevel['key'] }> {
  return apiPut('/ai/level', { level }, csrfToken)
}
