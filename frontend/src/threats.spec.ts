import {
  BASIS,
  EXPOSURE_CHOICES,
  clearSentence,
  importanceSentence,
  callSentence,
  coverageSentence,
  draftOf,
  firstLane,
  funnelSentence,
  funnelSteps,
  laneRows,
  laneSentence,
  portsOf,
  reachOf,
  sameDraft,
  threatSentence,
  verdictOf,
} from '@/threats'
import { coverage, funnel, threatPreview, threatSettings } from '@/test/threats'

describe('funnelSteps', () => {
  it('goes from the reports to where the incidents stand', () => {
    const steps = funnelSteps(funnel())

    expect(steps.map(({ key, count }) => [key, count])).toEqual([
      ['reports', 70_412],
      ['alerts', 1_204],
      ['incidents', 63],
      ['threat', 2],
      ['suspect', 5],
      ['background', 50],
    ])
    expect(steps[1]?.detail).toBe(
      '31,000 were another program saying the same thing, and 38,208 the same alert again.',
    )
  })

  it('draws the bars by the number of digits, so a few are not lost beside thousands', () => {
    const [reports, alerts, , threats] = funnelSteps(funnel())

    expect(reports?.width).toBe(100)
    expect(alerts?.width).toBeGreaterThan(50)
    expect(threats?.width).toBeGreaterThanOrEqual(4)
    expect(threats?.width).toBeLessThan(alerts?.width ?? 0)
  })

  it('draws nothing for none, and no bar is wider than the reports', () => {
    const steps = funnelSteps(funnel({ threats: 0 }))

    expect(steps[3]?.width).toBe(0)
    expect(funnelSteps(funnel({ reports: 0, alerts: 0 }))[0]?.width).toBe(0)
  })
})

describe('funnelSentence', () => {
  const last = 'the last 24 hours'

  it('says how the reports came down to threats and suspects', () => {
    expect(funnelSentence(funnel(), last)).toBe(
      '70,412 reports in the last 24 hours came to 1,204 alerts, grouped into 63 incidents: 2 threats and 5 suspects.',
    )
  })

  it('says one of each in the singular', () => {
    expect(
      funnelSentence(
        funnel({ reports: 1, alerts: 1, incidents: 1, threats: 1, suspects: 1 }),
        last,
      ),
    ).toBe('1 alert in the last 24 hours, grouped into 1 incident: 1 threat and 1 suspect.')
  })

  it('says when nothing needs a look', () => {
    expect(funnelSentence(funnel({ threats: 0, suspects: 0 }), last)).toContain(
      'None of them is a threat or worth a look.',
    )
  })

  it('says when nothing was reported', () => {
    expect(funnelSentence(funnel({ reports: 0 }), last)).toBe(
      'No program reported anything in the last 24 hours.',
    )
  })

  it('says it in the singular when many reports came to one alert', () => {
    expect(funnelSentence(funnel({ reports: 9, alerts: 1, incidents: 1 }), last)).toContain(
      '9 reports in the last 24 hours came to 1 alert, grouped into 1 incident',
    )
  })

  it('says one alert reported once is one alert', () => {
    expect(funnelSentence(funnel({ reports: 5, alerts: 5, incidents: 2 }), last)).toContain(
      '5 alerts in the last 24 hours, grouped into 2 incidents',
    )
  })
})

describe('coverageSentence', () => {
  it('says how many kinds have been judged', () => {
    expect(coverageSentence(coverage({ waiting: 0, owned: 3, judged: 6 }), true)).toBe(
      '9 of 9 kinds have been judged.',
    )
  })

  it('says the AI will get to those that wait, when it is watching', () => {
    expect(coverageSentence(coverage(), true)).toBe(
      '7 of 9 kinds have been judged. 2 are waiting for the AI.',
    )
  })

  it('says what to do about those that wait when no AI is watching', () => {
    expect(coverageSentence(coverage(), false)).toContain('turn on the AI')
  })

  it('has nothing to say of none', () => {
    expect(coverageSentence(coverage({ families: 0 }), true)).toBe(
      'There are no kinds of incident to judge.',
    )
  })
})

describe('firstLane', () => {
  it('opens on the first lane with something in it', () => {
    expect(firstLane(null)).toBe('threat')
    expect(firstLane(funnel())).toBe('threat')
    expect(firstLane(funnel({ threats: 0 }))).toBe('suspect')
    expect(firstLane(funnel({ threats: 0, suspects: 0 }))).toBe('background')
  })
})

describe('what is thought of a kind', () => {
  it('goes by your word first, then the AI’s, else says no one has judged it', () => {
    expect(
      verdictOf({ owner_call: 'background', classification: 'probe', confidence: 90 }),
    ).toEqual({ who: 'owner', text: 'You set it aside' })
    expect(verdictOf({ owner_call: null, classification: 'probe', confidence: 90 })).toEqual({
      who: 'ai',
      text: 'AI: Probe, 90% sure',
    })
    expect(verdictOf({ owner_call: null, classification: 'noise', confidence: null })).toEqual({
      who: 'ai',
      text: 'AI: Harmless',
    })
    expect(verdictOf({ owner_call: null, classification: null, confidence: null })).toEqual({
      who: 'none',
      text: 'Not judged yet',
    })
  })

  it('says whose word a call on an incident is', () => {
    expect(callSentence({ classification: 'probe', confidence: 92, basis: 'family' })).toBe(
      `Probe, 92% sure. ${BASIS.family.sentence}`,
    )
  })

  it('says where a kind is from', () => {
    expect(reachOf('internet').label).toBe('From the internet')
    expect(reachOf('network').label).toBe('Inside your network')
    expect(reachOf('rule').label).toBe('A rule with no address')
  })
})

describe('importanceSentence', () => {
  it('says what moving the bar for important devices means', () => {
    expect(importanceSentence('drop', 0)).toContain('same bar as any other')
    expect(importanceSentence('drop', 1)).toBe(
      'An incident that touched an important device is shown when AresGate is 1 point less sure than usual.',
    )
    expect(importanceSentence('drop', 10)).toContain('10 points less sure')
  })

  it('says what moving the bar for guests and gadgets means, and what it never hides', () => {
    expect(importanceSentence('raise', 0)).toContain('same bar as any other')
    expect(importanceSentence('raise', 15)).toContain('needs 15 points more before it is shown')
    expect(importanceSentence('raise', 15)).toContain('chain of attacks is shown regardless')
  })
})

describe('the settings page', () => {
  it('starts from what is kept, and notices any difference', () => {
    const kept = threatSettings({ exposed_ports: [22, 443] })
    const draft = draftOf(kept)

    expect(sameDraft(draft, draftOf(kept))).toBe(true)
    expect(draft.exposed_ports).not.toBe(kept.exposed_ports)
    for (const change of [
      { threat_from: 70 },
      { ai_may_clear: false },
      { clear_from: 90 },
      { ai_confirms: false },
      { ai_gives_verdicts: true },
      { exposure: 'none' as const },
      { notes: 'A web server' },
      { exposed_ports: [22] },
      { exposed_ports: [22, 80] },
      { important_drop: 20 },
      { low_raise: 5 },
    ]) {
      expect(sameDraft({ ...draft, ...change }, draftOf(kept))).toBe(false)
    }
  })

  it('reads ports from a field: once each, in order, and says which words are not ports', () => {
    expect(portsOf('443, 22 80;22')).toEqual({ ports: [22, 80, 443], bad: [] })
    expect(portsOf('')).toEqual({ ports: [], bad: [] })
    expect(portsOf('22, http, 0, 70000, 8080')).toEqual({
      ports: [22, 8080],
      bad: ['http', '0', '70000'],
    })
  })

  it('has a way to say each thing about exposure', () => {
    expect(EXPOSURE_CHOICES.map(({ value }) => value)).toEqual(['none', 'some', 'unknown'])
  })

  it('says what the bar for a threat means', () => {
    expect(threatSentence(50, 65)).toContain('Lower than usual')
    expect(threatSentence(90, 65)).toContain('Higher than usual')
    expect(threatSentence(65, 65)).toContain('The usual')
    expect(threatSentence(65, 65)).toContain('at least 65 out of 100')
  })

  it('says what the AI’s bar means', () => {
    expect(clearSentence(80, 50)).toContain('The surer it has to be')
    expect(clearSentence(50, 50)).toContain('As low as it can go.')
  })

  it('lists the lanes now and with the settings as asked', () => {
    expect(laneRows(threatPreview()).map((row) => [row.key, row.now, row.after])).toEqual([
      ['threats', 2, 3],
      ['suspects', 5, 4],
      ['background', 50, 50],
      ['cleared', 40, 40],
      ['muted', 4, 4],
    ])
  })

  it('says what saving would do to the lanes', () => {
    expect(laneSentence(threatPreview())).toBe(
      'Saving would change the lanes by +1 threat, −1 suspect.',
    )
    expect(
      laneSentence(
        threatPreview({
          after: { threats: 0, suspects: 5, background: 54, cleared: 40, muted: 4 },
        }),
      ),
    ).toBe('Saving would change the lanes by −2 threats, +4 in the background.')
  })

  it('says when nothing would move', () => {
    const same = threatPreview().now
    expect(laneSentence({ now: same, after: same })).toBe(
      'Nothing that is going on now would move to another lane.',
    )
  })
})
