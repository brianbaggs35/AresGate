import {
  ALL,
  changeSentence,
  draftOf,
  filteredOut,
  floorSentence,
  levelOf,
  rowsOf,
  sameDraft,
  weekSentence,
  withFloor,
} from '@/noiseFilters'
import { effect, noiseFilters, preview, source } from '@/test/noise'

const DRAFT = { confidence_floor: 35, quiet_inside: false, source_floors: {} }

describe('the draft', () => {
  it('begins as what is kept, with a floor only for the programs that have one', () => {
    const kept = noiseFilters({
      confidence_floor: 50,
      quiet_inside: true,
      sources: [source({ floor: 'high' }), source({ key: 'ntopng', name: 'ntopng' })],
    })

    expect(draftOf(kept)).toEqual({
      confidence_floor: 50,
      quiet_inside: true,
      source_floors: { wazuh: 'high' },
    })
  })

  it('is the same as another that says the same, in any order', () => {
    const one = { ...DRAFT, source_floors: { wazuh: 'high', ntopng: 'medium' } } as const
    const other = { ...DRAFT, source_floors: { ntopng: 'medium', wazuh: 'high' } } as const

    expect(sameDraft(one, other)).toBe(true)
  })

  it.each([
    ['the floor', { ...DRAFT, confidence_floor: 40 }],
    ['inside', { ...DRAFT, quiet_inside: true }],
    ['a program with a floor', { ...DRAFT, source_floors: { wazuh: 'high' } }],
  ] as const)('is not the same when %s differs', (_what, other) => {
    expect(sameDraft(DRAFT, other)).toBe(false)
    expect(sameDraft(other, DRAFT)).toBe(false)
  })

  it('is not the same when the programs are others, or a floor is another', () => {
    const one = { ...DRAFT, source_floors: { wazuh: 'high' } } as const

    expect(sameDraft(one, { ...DRAFT, source_floors: { ntopng: 'high' } })).toBe(false)
    expect(sameDraft(one, { ...DRAFT, source_floors: { wazuh: 'critical' } })).toBe(false)
  })

  it('sets a floor for a program, changes it and takes it off', () => {
    const set = withFloor(DRAFT, 'wazuh', 'high')
    expect(set.source_floors).toEqual({ wazuh: 'high' })

    const changed = withFloor(set, 'wazuh', 'critical')
    expect(changed.source_floors).toEqual({ wazuh: 'critical' })

    const kept = withFloor(changed, 'ntopng', 'medium')
    expect(kept.source_floors).toEqual({ wazuh: 'critical', ntopng: 'medium' })

    expect(withFloor(kept, 'wazuh', ALL).source_floors).toEqual({ ntopng: 'medium' })
    // The draft it was made from is not changed.
    expect(set.source_floors).toEqual({ wazuh: 'high' })
  })
})

describe('what a floor means', () => {
  it.each([
    [10, 'low'],
    [34, 'low'],
    [35, 'medium'],
    [64, 'medium'],
    [65, 'high'],
    [95, 'high'],
  ])('puts %i at %s', (floor, level) => {
    expect(levelOf(floor, 35, 65)).toBe(level)
  })

  it('says it in a sentence, and what the level means for how much is asked', () => {
    expect(floorSentence(35, 35, 65)).toContain('at least 35 sure it is real')
    expect(floorSentence(35, 35, 65)).toContain('medium confidence and up')
    expect(floorSentence(15, 35, 65)).toContain('Low is a long way down')
    expect(floorSentence(70, 35, 65)).toContain('nearly sure')
  })
})

describe('what a program reported', () => {
  it('lists it most serious first, with thousands separated', () => {
    expect(weekSentence(source())).toBe('Last 7 days: 12 high, 150 medium, 2,901 low.')
  })

  it('says when there was nothing', () => {
    expect(weekSentence(source({ week: {} }))).toBe('Nothing in the last 7 days.')
  })
})

describe('what the filters would do', () => {
  it('counts the incidents that are filtered out as the unsure and the muted ones', () => {
    expect(filteredOut(effect())).toBe(26)
  })

  it('sets the figures beside each other', () => {
    expect(rowsOf(preview())).toEqual([
      { key: 'needs-you', label: 'Incidents that need you', now: 5, after: 2 },
      { key: 'filtered-out', label: 'Incidents filtered out', now: 26, after: 29 },
      { key: 'set-aside', label: 'Alerts set aside inside them', now: 0, after: 2901 },
    ])
  })

  it('says what changed in a sentence', () => {
    expect(changeSentence(preview())).toBe(
      'With these settings 2 incidents would need you instead of 5, and 2,901 alerts would be set aside.',
    )
  })

  it('says so when the same number would still need you, and counts one properly', () => {
    const same = preview({
      after: effect({
        set_aside: { total: 1, inside: 1, severity: 0, by_source: { wazuh: 1 } },
      }),
    })

    expect(changeSentence(same)).toBe(
      'With these settings 5 incidents would still need you, and 1 alert would be set aside.',
    )
  })

  it('counts one incident properly', () => {
    const one = preview({
      after: effect({ incidents: { active: 1, needs_you: 1, urgent: 0, unsure: 0, muted: 0 } }),
    })

    expect(changeSentence(one)).toContain('1 incident would need you instead of 5')
  })
})
