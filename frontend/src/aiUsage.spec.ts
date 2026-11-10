import {
  cachedShare,
  costWords,
  dailySeries,
  dayLabel,
  dollarsOf,
  formatMetric,
  formatMoney,
  formatTokens,
  groupSeries,
  limitColor,
  limitName,
  limitPercent,
  limitWords,
  purposeLabel,
  RANGES,
  tokensOf,
} from '@/aiUsage'
import { group, limit, totals, usage } from '@/test/aiUsage'

describe('money', () => {
  it.each([
    [0, '$0.00'],
    [1_500_000, '$1.50'],
    [41_500, '$0.04'],
    [2_500, '$0.0025'],
    [10_000, '$0.01'],
  ])('writes %d millionths as %s', (micros, written) => {
    expect(formatMoney(micros)).toBe(written)
  })

  it('writes an amount that is not known as a dash', () => {
    expect(formatMoney(null)).toBe('–')
  })

  it('writes a limit as it is typed', () => {
    expect(dollarsOf(2_500_000)).toBe('2.5')
    expect(dollarsOf(null)).toBe('')
  })
})

describe('counts', () => {
  it('writes tokens in full while they fit and short after', () => {
    expect(formatTokens(9_999)).toBe('9,999')
    expect(formatTokens(27_600)).toBe('27.6K')
  })

  it('adds what was sent and what came back', () => {
    expect(tokensOf(totals())).toBe(27_600)
  })

  it('says how much of what was sent was cached', () => {
    expect(cachedShare(totals())).toBe(25)
    expect(cachedShare(totals({ input_tokens: 0, cached_tokens: 0 }))).toBe(0)
  })
})

describe('names', () => {
  it('names the uses it knows and writes out the others', () => {
    expect(purposeLabel('triage')).toBe('Reading incidents')
    expect(purposeLabel('chat')).toBe('Chat')
    expect(purposeLabel('agent')).toBe('Agents')
    expect(purposeLabel('weekly_report')).toBe('Weekly report')
  })

  it('offers three ranges, each saying what comes before it', () => {
    expect(RANGES.map(({ key, before }) => [key, before])).toEqual([
      ['7d', 'the 7 days before'],
      ['30d', 'the 30 days before'],
      ['90d', 'the 90 days before'],
    ])
  })

  it('names a day by its month and date', () => {
    expect(dayLabel('2026-11-03T12:00:00Z')).toBe('Nov 3')
  })
})

describe('the charts', () => {
  it('stacks the days by use, in the metric asked for', () => {
    const cost = dailySeries(usage(), 'cost')
    const tokens = dailySeries(usage(), 'tokens')
    const calls = dailySeries(usage(), 'calls')

    expect(cost).toHaveLength(1)
    expect(cost[0]).toMatchObject({ id: 'triage', label: 'Reading incidents' })
    expect(cost[0]?.values).toEqual([0, 0.007, 0.01, 0, 0.017, 0, 0.0075])
    expect(tokens[0]?.values).toEqual([0, 4_000, 6_000, 0, 10_000, 0, 7_600])
    expect(calls[0]?.values).toEqual([0, 2, 3, 0, 5, 0, 2])
  })

  it('draws a bar for each group', () => {
    const groups = [group(), group({ key: 'b', cost_micros: 1_000_000, tokens: 5, calls: 2 })]

    expect(groupSeries(groups, 'cost')).toEqual([
      { id: 'cost', label: 'Cost', values: [0.0415, 1] },
    ])
    expect(groupSeries(groups, 'tokens')[0]?.values).toEqual([27_600, 5])
    expect(groupSeries(groups, 'calls')[0]?.values).toEqual([12, 2])
  })

  it('reads a value the way the metric does', () => {
    expect(formatMetric('cost')(1.5)).toBe('$1.50')
    expect(formatMetric('tokens')(27_600)).toBe('27.6K')
    expect(formatMetric('calls')(1_284)).toBe('1,284')
  })
})

describe('the limits', () => {
  it('names them and says where each stands', () => {
    const day = limit({ limit_micros: 2_000_000, spent_micros: 500_000, state: 'ok' })

    expect(limitName(day)).toBe('Daily limit')
    expect(limitName(limit({ period: 'month' }))).toBe('Monthly limit')
    expect(limitWords(limit())).toBe('$0.01 spent, with no limit')
    expect(limitWords(day)).toBe('$0.50 of $2.00')
    expect(limitWords({ ...day, state: 'warning' })).toBe('$0.50 of $2.00: nearly used up')
    expect(limitWords({ ...day, state: 'reached' })).toBe(
      '$0.50 of $2.00: used up, so requests are stopped',
    )
  })

  it('works out how much is gone, never more than all', () => {
    expect(limitPercent(limit())).toBe(0)
    expect(limitPercent(limit({ limit_micros: 0 }))).toBe(0)
    expect(limitPercent(limit({ limit_micros: 4_000_000, spent_micros: 1_000_000 }))).toBe(25)
    expect(limitPercent(limit({ limit_micros: 1_000_000, spent_micros: 3_000_000 }))).toBe(100)
  })

  it('colors the meter by state', () => {
    expect(limitColor('ok')).toBe('primary')
    expect(limitColor('none')).toBe('primary')
    expect(limitColor('warning')).toBe('warning')
    expect(limitColor('reached')).toBe('error')
  })
})

describe('cost in words', () => {
  it('is the cost where every call has a price', () => {
    expect(costWords(1_500_000, 0)).toBe('$1.50')
  })

  it('says which calls have none', () => {
    expect(costWords(0, 2)).toBe('2 without a price')
    expect(costWords(1_500_000, 1)).toBe('$1.50 and 1 without a price')
  })
})
