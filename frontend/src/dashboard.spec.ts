import type { Collector, CollectorsReport } from '@/api/collectors'
import type { AlertCounts } from '@/api/dashboard'
import {
  bucketLabel,
  changeOf,
  collectionOf,
  filteredOut,
  marksOf,
  alertsHint,
  needsYouLink,
  needsYouQuery,
  postureOf,
  sumBuckets,
} from '@/dashboard'
import { attention, incidentMark } from '@/test/dashboard'

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
  return {
    total,
    previous: 0,
    reports: total,
    duplicates: 0,
    highest: null,
    by_severity: bySeverity,
  }
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
  const none = attention()

  it('asks for something to be connected before anything else', () => {
    const posture = postureOf(
      alertsOf({ critical: [1, 0, 0] }),
      attention({ incidents: 1, needs_you: 1, urgent: 1 }),
      collectionOf(report([])),
      '24h',
    )
    expect(posture.state).toBe('setup')
    expect(posture.title).toBe('Nothing is watching yet')
  })

  it('needs attention for incidents it is confident of, and says how many more are worth a look', () => {
    expect(
      postureOf(
        alertsOf({ high: [1, 1, 0] }),
        attention({ incidents: 3, needs_you: 1, urgent: 1 }),
        well,
        '24h',
      ),
    ).toEqual({
      state: 'attention',
      title: 'Needs your attention',
      detail: '1 incident that AresGate is confident is real in the last 24 hours.',
    })
    expect(
      postureOf(
        alertsOf({ high: [1, 1, 0] }),
        attention({ incidents: 9, needs_you: 5, urgent: 2 }),
        well,
        '7d',
      ).detail,
    ).toBe(
      '2 incidents that AresGate is confident are real in the last 7 days, and 3 more worth a look.',
    )
  })

  it('goes by the incidents and not by how many alerts there were', () => {
    const thousands = alertsOf({ high: [3000, 642, 0] })
    expect(postureOf(thousands, none, well, '24h')).toEqual({
      state: 'calm',
      title: 'All quiet',
      detail: '3,642 alerts in the last 24 hours, and none of them needs you.',
    })
  })

  it('adds that collectors are down to an alarm', () => {
    expect(
      postureOf(alertsOf({}), attention({ incidents: 1, needs_you: 1, urgent: 1 }), failing, '24h')
        .detail,
    ).toBe(
      '1 incident that AresGate is confident is real in the last 24 hours. 1 collector is not working, so a quiet network may not be a safe one.',
    )
  })

  it('is worth a look for incidents it is not sure are attacks', () => {
    expect(postureOf(alertsOf({}), attention({ incidents: 2, needs_you: 2 }), well, '24h')).toEqual(
      {
        state: 'watch',
        title: 'Worth a look',
        detail:
          '2 incidents to look at in the last 24 hours, none that AresGate is confident is a real attack.',
      },
    )
    expect(
      postureOf(alertsOf({}), attention({ incidents: 1, needs_you: 1 }), failing, '7d').detail,
    ).toBe(
      '1 incident to look at in the last 7 days, none that AresGate is confident is a real attack. 1 collector is not working, so a quiet network may not be a safe one.',
    )
  })

  it("never says it is quiet while collectors aren't working", () => {
    expect(postureOf(alertsOf({}), none, failing, '24h')).toEqual({
      state: 'watch',
      title: "Some sources aren't reporting",
      detail:
        'No alerts in the last 24 hours. 1 collector is not working, so a quiet network may not be a safe one.',
    })
    expect(postureOf(alertsOf({ low: [2, 0, 0] }), none, failing, '24h').detail).toMatch(
      /^2 alerts in the last 24 hours, and none of them needs you\. 1 collector/,
    )
  })

  it('is quiet when there is nothing, and when there is nothing that needs you', () => {
    expect(postureOf(alertsOf({}), none, well, '24h')).toEqual({
      state: 'calm',
      title: 'All quiet',
      detail: 'No alerts in the last 24 hours.',
    })
    expect(
      postureOf(
        alertsOf({ info: [1, 0, 0], low: [0, 1, 0] }),
        attention({ incidents: 4, handled: 1, muted: 1, unsure: 2 }),
        well,
        '7d',
      ),
    ).toEqual({
      state: 'calm',
      title: 'All quiet',
      detail: '2 alerts in the last 7 days, and none of them needs you.',
    })
    expect(postureOf(alertsOf({ low: [1, 0, 0] }), none, well, '24h').detail).toBe(
      '1 alert in the last 24 hours, and none of them needs you.',
    )
  })
})

describe('filteredOut', () => {
  const since = '2026-11-01T10:00:00Z'

  it('lists the reasons there are incidents for, each as a link to those incidents', () => {
    const reasons = filteredOut(
      attention({ incidents: 12, unsure: 7, muted: 3, handled: 2 }),
      since,
    )
    expect(reasons.map(({ key, count, label }) => [key, count, label])).toEqual([
      ['unsure', 7, 'not sure enough'],
      ['muted', 3, 'called not suspicious or low priority'],
      ['handled', 2, 'already handled'],
    ])
    expect(reasons.map(({ to }) => to)).toEqual([
      { name: 'incidents', query: { q: `since:${since} confidence<35` } },
      {
        name: 'incidents',
        query: { quieted: '1', q: `since:${since} verdict:not_suspicious,low_priority` },
      },
      {
        name: 'incidents',
        query: { view: 'all', quieted: '1', q: `since:${since} status:resolved,dismissed` },
      },
    ])
  })

  it('leaves out the reasons nothing was filtered for, and uses the floor it was given', () => {
    const reasons = filteredOut(attention({ incidents: 4, unsure: 4, floor: 50 }), since)
    expect(reasons).toHaveLength(1)
    expect(reasons[0]?.to).toEqual({
      name: 'incidents',
      query: { q: `since:${since} confidence<50` },
    })
    expect(filteredOut(attention(), since)).toEqual([])
  })
})

describe('needsYou', () => {
  const since = '2026-11-01T10:00:00Z'

  it('asks for what the banner counts: the threats and the suspects in the window', () => {
    expect(needsYouQuery(since, 3)).toEqual({
      lanes: ['threat', 'suspect'],
      q: `since:${since}`,
      tz: expect.any(String) as string,
      limit: 3,
      order: 'priority',
    })
  })

  it('links to the Threats page, open on the lane that matters most', () => {
    expect(needsYouLink(attention({ urgent: 1 }))).toEqual({
      name: 'threats',
      query: { lane: 'threat' },
    })
    expect(needsYouLink(attention({ urgent: 0, needs_you: 2 }))).toEqual({
      name: 'threats',
      query: { lane: 'suspect' },
    })
  })
})

describe('alertsHint', () => {
  it('names the window', () => {
    expect(alertsHint({ total: 5, reports: 5 }, 'the last 24 hours')).toBe('In the last 24 hours')
  })

  it('says how many reports they came from when programs reported things more than once', () => {
    expect(alertsHint({ total: 1_204, reports: 70_412 }, 'the last 24 hours')).toBe(
      'In the last 24 hours, from 70,412 reports',
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

describe('marksOf', () => {
  it('flags an incident at the time it began, saying what it is and where it leads', () => {
    const [mark] = marksOf([incidentMark({ id: 7, severity: 'critical' })], 'en-US')

    expect(mark).toMatchObject({
      id: 'incident-7',
      time: Date.parse('2026-10-26T14:15:00Z'),
      label: 'Critical incident: Brute force on ssh (93.184.216.34)',
      color: 'var(--chart-severity-critical)',
      to: { name: 'incident', params: { id: 7 } },
    })
    expect(mark?.heading).toMatch(/^Began Oct 26, 2026/)
    expect(mark?.rows).toEqual([
      {
        value: 'Critical',
        label: 'Brute force on ssh (93.184.216.34)',
        color: 'var(--chart-severity-critical)',
      },
      { value: '70 of 100', label: 'sure it is an attack' },
    ])
  })

  it('says when an integration banned the address', () => {
    const [mark] = marksOf([incidentMark({ banned: true })])

    expect(mark?.rows.at(-1)).toEqual({ value: 'Banned', label: 'by an integration' })
  })

  it('weighs the more serious first, and of two as serious the surer', () => {
    const [low, sure, unsure, critical] = marksOf([
      incidentMark({ severity: 'medium', confidence: 99 }),
      incidentMark({ severity: 'high', confidence: 80 }),
      incidentMark({ severity: 'high', confidence: 40 }),
      incidentMark({ severity: 'critical', confidence: 10 }),
    ])

    const weights = [low, unsure, sure, critical].map((mark) => mark?.weight as number)
    expect(weights).toEqual([...weights].sort((a, b) => a - b))
  })

  it('has no flags for no incidents', () => {
    expect(marksOf([])).toEqual([])
  })
})
