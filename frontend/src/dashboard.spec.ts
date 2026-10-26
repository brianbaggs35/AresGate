import type { Collector, CollectorsReport } from '@/api/collectors'
import type { AlertCounts } from '@/api/dashboard'
import { bucketLabel, changeOf, collectionOf, postureOf, sumBuckets } from '@/dashboard'

const BEFORE = 'the day before'

function alertsOf(counts: Partial<AlertCounts['by_severity']>, buckets = 3): AlertCounts {
  const empty = () => new Array<number>(buckets).fill(0)
  const bySeverity = {
    info: empty(),
    low: empty(),
    medium: empty(),
    high: empty(),
    critical: empty(),
    ...counts,
  }
  const total = Object.values(bySeverity).reduce(
    (sum, row) => sum + row.reduce((a, b) => a + b, 0),
    0,
  )
  return { total, previous: 0, highest: null, by_severity: bySeverity }
}

function collector(state: Collector['state']): Collector {
  return { collector: 'job', state } as Collector
}

function report(
  states: Collector['state'][],
  worker: CollectorsReport['worker']['state'] = 'running',
): CollectorsReport {
  return {
    worker: { state: worker, started_at: null, seen_at: null },
    collectors: states.map(collector),
  }
}

describe('changeOf', () => {
  it('says nothing changed, and that there were none when there were none', () => {
    expect(changeOf(0, 0, BEFORE, true)).toEqual({
      text: 'None, as in the day before',
      direction: 'flat',
      tone: 'neutral',
    })
    expect(changeOf(7, 7, BEFORE, true)).toEqual({
      text: 'The same as the day before',
      direction: 'flat',
      tone: 'neutral',
    })
  })

  it('gives a percentage, and calls more bad only where more is worse', () => {
    expect(changeOf(15, 10, BEFORE, true)).toEqual({
      text: '50% more than the day before',
      direction: 'up',
      tone: 'bad',
    })
    expect(changeOf(15, 10, BEFORE, false)).toMatchObject({ direction: 'up', tone: 'neutral' })
    expect(changeOf(5, 10, BEFORE, true)).toEqual({
      text: '50% fewer than the day before',
      direction: 'down',
      tone: 'good',
    })
    expect(changeOf(5, 10, BEFORE, false)).toMatchObject({ direction: 'down', tone: 'neutral' })
  })

  it('says it is up from none rather than dividing by zero', () => {
    expect(changeOf(3, 0, BEFORE, true)).toEqual({
      text: 'Up from none the day before',
      direction: 'up',
      tone: 'bad',
    })
  })

  it('calls a change under half a percent the same', () => {
    expect(changeOf(1_001, 1_000, BEFORE, true)).toEqual({
      text: 'About the same as the day before',
      direction: 'flat',
      tone: 'neutral',
    })
  })
})

describe('sumBuckets', () => {
  it('adds every severity in each bucket', () => {
    expect(
      sumBuckets(alertsOf({ low: [1, 0, 2], critical: [0, 0, 1], info: [4, 0, 0] }).by_severity),
    ).toEqual([5, 0, 3])
  })
})

describe('collectionOf', () => {
  it('has nothing to say about collectors that are not there', () => {
    expect(collectionOf(report([]))).toEqual({
      state: 'none',
      total: 0,
      label: 'None',
      trouble: null,
    })
  })

  it('is well when every collector works or has not run yet', () => {
    expect(collectionOf(report(['ok', 'waiting']))).toEqual({
      state: 'ok',
      total: 2,
      label: 'Working',
      trouble: null,
    })
  })

  it('says they are starting while none of them has run yet', () => {
    expect(collectionOf(report(['waiting']))).toMatchObject({ state: 'ok', label: 'Starting' })
    expect(collectionOf(report(['waiting', 'ok']))).toMatchObject({ label: 'Working' })
  })

  it('counts the collectors that failed or are overdue', () => {
    expect(collectionOf(report(['ok', 'problem']))).toEqual({
      state: 'problem',
      total: 2,
      label: '1 failing',
      trouble: '1 collector is not working',
    })
    expect(collectionOf(report(['late', 'problem', 'ok']))).toMatchObject({
      label: '2 failing',
      trouble: '2 collectors are not working',
    })
  })

  it('is not well while the worker that runs them has stopped', () => {
    expect(collectionOf(report(['ok'], 'stopped'))).toEqual({
      state: 'problem',
      total: 1,
      label: 'Stopped',
      trouble: 'The collector worker has stopped',
    })
  })
})

describe('postureOf', () => {
  const well = collectionOf(report(['ok']))
  const failing = collectionOf(report(['problem']))

  it('asks for something to be connected before anything else', () => {
    const posture = postureOf(alertsOf({ critical: [1, 0, 0] }), collectionOf(report([])), '24h')
    expect(posture.state).toBe('setup')
    expect(posture.title).toBe('Nothing is watching yet')
  })

  it('needs attention for a high or critical alert, whatever else there is', () => {
    expect(postureOf(alertsOf({ high: [1, 1, 0] }), well, '24h')).toEqual({
      state: 'attention',
      title: 'Needs your attention',
      detail: '2 serious alerts in the last 24 hours (high or critical).',
    })
    expect(postureOf(alertsOf({ critical: [0, 0, 1], medium: [3, 0, 0] }), well, '7d').detail).toBe(
      '1 serious alert in the last 7 days (high or critical).',
    )
  })

  it('adds that collectors are down to an alarm', () => {
    expect(postureOf(alertsOf({ high: [1, 0, 0] }), failing, '24h').detail).toBe(
      '1 serious alert in the last 24 hours (high or critical). 1 collector is not working, so a quiet network may not be a safe one.',
    )
  })

  it('is worth a look for medium alerts and says none were serious', () => {
    expect(postureOf(alertsOf({ medium: [2, 0, 0] }), well, '24h')).toEqual({
      state: 'watch',
      title: 'Worth a look',
      detail: '2 medium alerts in the last 24 hours, none serious.',
    })
    expect(postureOf(alertsOf({ medium: [1, 0, 0] }), failing, '24h').detail).toContain(
      '1 medium alert in the last 24 hours, none serious. 1 collector is not working',
    )
  })

  it("never says it is quiet while collectors aren't working", () => {
    expect(postureOf(alertsOf({}), failing, '24h')).toEqual({
      state: 'watch',
      title: "Some sources aren't reporting",
      detail:
        'No alerts in the last 24 hours. 1 collector is not working, so a quiet network may not be a safe one.',
    })
    expect(postureOf(alertsOf({ low: [2, 0, 0] }), failing, '24h').detail).toMatch(
      /^2 minor alerts in the last 24 hours\. 1 collector/,
    )
  })

  it('is quiet when there is nothing, and when there is only little', () => {
    expect(postureOf(alertsOf({}), well, '24h')).toEqual({
      state: 'calm',
      title: 'All quiet',
      detail: 'No alerts in the last 24 hours.',
    })
    expect(postureOf(alertsOf({ info: [1, 0, 0], low: [0, 1, 0] }), well, '7d')).toEqual({
      state: 'calm',
      title: 'All quiet',
      detail: '2 minor alerts in the last 7 days. Nothing that needs you.',
    })
    expect(postureOf(alertsOf({ low: [1, 0, 0] }), well, '24h').detail).toBe(
      '1 minor alert in the last 24 hours. Nothing that needs you.',
    )
  })
})

describe('bucketLabel', () => {
  it('gives the hour for a day and the day and hour for a week', () => {
    expect(bucketLabel('2026-10-26T14:00:00Z', '24h', 'en-US')).toMatch(/^\d{1,2}\s?[AP]M$/)
    // Newer Unicode data drops the comma after the day, so either is the right answer.
    expect(bucketLabel('2026-10-26T14:00:00Z', '7d', 'en-US')).toMatch(
      /^[A-Z][a-z]{2},? \d{1,2}\s?[AP]M$/,
    )
  })
})
