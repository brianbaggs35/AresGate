import type {
  Usage,
  UsageCall,
  UsageCallDetail,
  UsageCallPage,
  UsageGroup,
  UsageLevel,
  UsageLimit,
  UsageTotals,
} from '@/api/aiUsage'

/** What the usage API answers, for tests of the pages that show it. */

export function totals(over: Partial<UsageTotals> = {}): UsageTotals {
  return {
    calls: 12,
    failed: 0,
    input_tokens: 24_000,
    cached_tokens: 6_000,
    output_tokens: 3_600,
    cost_micros: 41_500,
    unpriced: 0,
    ...over,
  }
}

export function limit(over: Partial<UsageLimit> = {}): UsageLimit {
  return { period: 'day', limit_micros: null, spent_micros: 12_000, state: 'none', ...over }
}

export function group(over: Partial<UsageGroup> = {}): UsageGroup {
  return {
    key: 'claude-haiku-5-5',
    label: 'Claude Haiku 5.5',
    provider: 'anthropic',
    calls: 12,
    tokens: 27_600,
    cost_micros: 41_500,
    unpriced: 0,
    ...over,
  }
}

/** The levels as the server words them. */
export function levels(): UsageLevel[] {
  return [
    {
      key: 'very_low',
      label: 'Very low',
      summary: 'Reads nothing by itself. AI answers only when you ask.',
      per_hour: 0,
    },
    {
      key: 'low',
      label: 'Low',
      summary: 'Reads incidents rated high or higher, up to 6 an hour. Reads each one once.',
      per_hour: 6,
    },
    {
      key: 'medium',
      label: 'Medium',
      summary: 'Reads incidents rated medium or higher, up to 20 an hour.',
      per_hour: 20,
    },
    {
      key: 'high',
      label: 'High',
      summary: 'Reads incidents rated low or higher, up to 60 an hour.',
      per_hour: 60,
    },
    {
      key: 'maximum',
      label: 'Maximum',
      summary: 'Reads every incident, even the least serious, up to 150 an hour.',
      per_hour: 150,
    },
  ]
}

/** A month of use by reading incidents, on three days of the week. */
export function usage(over: Partial<Usage> = {}): Usage {
  const days = [
    '2026-11-09T04:00:00Z',
    '2026-11-10T04:00:00Z',
    '2026-11-11T04:00:00Z',
    '2026-11-12T04:00:00Z',
    '2026-11-13T04:00:00Z',
    '2026-11-14T04:00:00Z',
    '2026-11-15T04:00:00Z',
  ]
  return {
    range: '7d',
    start: days[0] as string,
    end: '2026-11-16T04:00:00Z',
    days,
    uses: [
      {
        purpose: 'triage',
        calls: [0, 2, 3, 0, 5, 0, 2],
        tokens: [0, 4_000, 6_000, 0, 10_000, 0, 7_600],
        cost_micros: [0, 7_000, 10_000, 0, 17_000, 0, 7_500],
      },
    ],
    totals: totals(),
    previous: totals({ calls: 6, input_tokens: 12_000, output_tokens: 1_800, cost_micros: 20_000 }),
    by_provider: [group({ key: 'anthropic', label: 'Anthropic', provider: null })],
    by_model: [group()],
    by_purpose: [group({ key: 'triage', label: 'triage', provider: null })],
    top: [
      {
        about: 'incident 12',
        purpose: 'triage',
        calls: 3,
        tokens: 6_900,
        cost_micros: 10_400,
        incident_id: 12,
      },
      {
        about: 'the weekly summary',
        purpose: 'summary',
        calls: 1,
        tokens: 900,
        cost_micros: 700,
        incident_id: null,
      },
    ],
    month: {
      start: '2026-11-01T00:00:00Z',
      end: '2026-12-01T00:00:00Z',
      spent_micros: 82_000,
      unpriced: 0,
      projected_micros: 160_000,
    },
    limits: [limit(), limit({ period: 'month', spent_micros: 82_000 })],
    level: 'medium',
    levels: levels(),
    prices: {
      as_of: '2026-10-27',
      sources: [
        { provider: 'Anthropic', url: 'https://platform.claude.com/docs/en/about-claude/pricing' },
        { provider: 'OpenAI', url: 'https://developers.openai.com/api/docs/pricing' },
      ],
    },
    ever: true,
    ...over,
  }
}

export function usageCall(over: Partial<UsageCall> = {}): UsageCall {
  return {
    id: 7,
    occurred_at: '2026-11-15T15:42:10Z',
    purpose: 'triage',
    about: 'incident 12',
    provider: 'anthropic',
    provider_label: 'Anthropic',
    model: 'claude-haiku-5-5',
    model_label: 'Claude Haiku 5.5',
    level: 'balanced',
    ok: true,
    input_tokens: 1_200,
    cached_tokens: 0,
    output_tokens: 300,
    cost_micros: 1_500,
    duration_ms: 1_800,
    truncated: false,
    error: null,
    ...over,
  }
}

export function callPage(count: number, total = count, first = 1): UsageCallPage {
  return {
    total,
    items: Array.from({ length: count }, (_, index) =>
      usageCall({ id: first + index, about: `incident ${first + index}` }),
    ),
  }
}

export function callDetail(over: Partial<UsageCallDetail> = {}): UsageCallDetail {
  return {
    ...usageCall(),
    prompt: 'HOST_1 was scanned by WAN_1 on port 22.',
    answer: 'HOST_1 was probed by WAN_1; nothing got in.',
    ...over,
  }
}
