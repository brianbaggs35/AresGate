import type { BarSeries } from '@/charts/BarChart.vue'
import { formatCompact, formatCount } from '@/format'
import type {
  LimitState,
  Usage,
  UsageGroup,
  UsageLimit,
  UsageRange,
  UsageTotals,
} from '@/api/aiUsage'

/** The stretches of time the page offers, with how it says the one before. */
export const RANGES: readonly { key: UsageRange; label: string; long: string; before: string }[] = [
  { key: '7d', label: '7 days', long: 'the last 7 days', before: 'the 7 days before' },
  { key: '30d', label: '30 days', long: 'the last 30 days', before: 'the 30 days before' },
  { key: '90d', label: '90 days', long: 'the last 90 days', before: 'the 90 days before' },
]

/** What the daily chart and the bars can show. */
export type Metric = 'cost' | 'tokens' | 'calls'

export const METRICS: readonly { key: Metric; label: string }[] = [
  { key: 'cost', label: 'Cost' },
  { key: 'tokens', label: 'Tokens' },
  { key: 'calls', label: 'Calls' },
]

const MICROS = 1_000_000

/** Money the way it is written: "$1.25", with more places for a very small amount, and "–" where
 * it isn't known. */
export function formatMoney(micros: number | null): string {
  if (micros === null) return '–'
  const dollars = micros / MICROS
  const places = dollars === 0 || dollars >= 0.01 ? 2 : 4
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  }).format(dollars)
}

/** Dollars, as a limit is typed and kept: "2.5" or "". */
export function dollarsOf(micros: number | null): string {
  return micros === null ? '' : String(micros / MICROS)
}

/** A count of tokens: in full while it fits, short from ten thousand. */
export function formatTokens(count: number): string {
  return count < 10_000 ? formatCount(count) : formatCompact(count)
}

const PURPOSES: Readonly<Record<string, string>> = {
  triage: 'Reading incidents',
  chat: 'Chat',
  summary: 'Summaries',
}

/** What a use of AI is called. A use that isn't known by name is written out as it is kept. */
export function purposeLabel(key: string): string {
  return PURPOSES[key] ?? key.charAt(0).toUpperCase() + key.slice(1).replaceAll('_', ' ')
}

/** All the tokens of a set of calls, counting what was sent and what came back. */
export function tokensOf(totals: UsageTotals): number {
  return totals.input_tokens + totals.output_tokens
}

/** How much of what was sent the provider already had cached, as a percentage. */
export function cachedShare(totals: UsageTotals): number {
  return totals.input_tokens === 0
    ? 0
    : Math.round((totals.cached_tokens / totals.input_tokens) * 100)
}

/** How a value of the metric reads, on an axis and in a tooltip. The cost chart works in dollars. */
export function formatMetric(metric: Metric): (value: number) => string {
  if (metric === 'cost') return (value) => formatMoney(Math.round(value * MICROS))
  if (metric === 'tokens') return (value) => formatTokens(value)
  return (value) => formatCount(value)
}

function valueOf(metric: Metric, item: { cost_micros: number; tokens: number; calls: number }) {
  if (metric === 'cost') return item.cost_micros / MICROS
  return metric === 'tokens' ? item.tokens : item.calls
}

/** The name of a day: "Nov 3". */
export function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(
    new Date(iso),
  )
}

/** What each use took on each day, as stacked bars: a series for each use. */
export function dailySeries(usage: Usage, metric: Metric): BarSeries[] {
  return usage.uses.map((use) => ({
    id: use.purpose,
    label: purposeLabel(use.purpose),
    values: use.calls.map((_, day) =>
      valueOf(metric, {
        cost_micros: use.cost_micros[day] as number,
        tokens: use.tokens[day] as number,
        calls: use.calls[day] as number,
      }),
    ),
  }))
}

/** One bar for each group: how much it took of the metric. */
export function groupSeries(groups: readonly UsageGroup[], metric: Metric): BarSeries[] {
  return [
    {
      id: metric,
      label: METRICS.find(({ key }) => key === metric)?.label ?? metric,
      values: groups.map((group) => valueOf(metric, group)),
    },
  ]
}

/** What kind of limit it is, in words. */
export function limitName(limit: UsageLimit): string {
  return limit.period === 'day' ? 'Daily limit' : 'Monthly limit'
}

/** Where the limit stands, as a sentence. */
export function limitWords(limit: UsageLimit): string {
  const spent = formatMoney(limit.spent_micros)
  const words: Record<LimitState, string> = {
    none: `${spent} spent, with no limit`,
    ok: `${spent} of ${formatMoney(limit.limit_micros)}`,
    warning: `${spent} of ${formatMoney(limit.limit_micros)}: nearly used up`,
    reached: `${spent} of ${formatMoney(limit.limit_micros)}: used up, so requests are stopped`,
  }
  return words[limit.state]
}

/** How much of a limit is gone, 0 to 100. */
export function limitPercent(limit: UsageLimit): number {
  if (limit.limit_micros === null || limit.limit_micros === 0) return 0
  return Math.min(100, Math.round((limit.spent_micros / limit.limit_micros) * 100))
}

/** The color of a limit's meter. */
export function limitColor(state: LimitState): 'primary' | 'warning' | 'error' {
  if (state === 'reached') return 'error'
  return state === 'warning' ? 'warning' : 'primary'
}

/** What a group of calls cost, or how many of them have no price to work it out from. */
export function costWords(cost: number, unpriced: number): string {
  if (unpriced === 0) return formatMoney(cost)
  const none = `${formatCount(unpriced)} without a price`
  return cost === 0 ? none : `${formatMoney(cost)} and ${none}`
}
