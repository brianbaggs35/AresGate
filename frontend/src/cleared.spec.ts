import type { ClearingStep } from '@/api/incidents'
import { CLEARED_LISTS, countOf, nudgeText, stepLine } from '@/cleared'

const step = (changes: Partial<ClearingStep> = {}): ClearingStep => ({
  action: 'cleared',
  at: '2026-06-01T12:00:00Z',
  by: 'the AI',
  verdict: 'not_suspicious',
  confidence: 91,
  ...changes,
})

describe('cleared', () => {
  it('has the two lists, each with what it says when empty', () => {
    expect(CLEARED_LISTS.map((each) => each.key)).toEqual(['waiting', 'cleared'])
    expect(CLEARED_LISTS.every((each) => each.empty.length > 0)).toBe(true)
  })

  it('counts a list', () => {
    expect(countOf({ waiting: 3, cleared: 5 }, 'cleared')).toBe(5)
  })

  describe('nudgeText', () => {
    it('says nothing when there is nothing', () => {
      expect(nudgeText({ waiting: 0, cleared: 0 })).toBeNull()
    })

    it('says what the AI cleared and what waits', () => {
      expect(nudgeText({ waiting: 0, cleared: 1 })).toBe(
        '1 incident cleared by the AI that is not confirmed.',
      )
      expect(nudgeText({ waiting: 1, cleared: 0 })).toBe(
        '1 incident the AI suggests clearing waits for you.',
      )
      expect(nudgeText({ waiting: 2, cleared: 3 })).toBe(
        '3 incidents cleared by the AI that are not confirmed, and 2 incidents the AI suggests clearing wait for you.',
      )
    })
  })

  describe('stepLine', () => {
    it('says what the AI cleared, and how sure it was', () => {
      expect(stepLine(step())).toBe('The AI cleared this as not suspicious (91% sure).')
      expect(stepLine(step({ verdict: 'low_priority', confidence: null }))).toBe(
        'The AI cleared this as low priority.',
      )
      expect(stepLine(step({ verdict: null }))).toBe('The AI cleared this (91% sure).')
    })

    it('says what the owner did about it', () => {
      expect(stepLine(step({ action: 'confirmed', by: 'brian', verdict: null }))).toBe(
        'brian confirmed it as the AI cleared it.',
      )
      expect(stepLine(step({ action: 'taken_back', by: 'brian' }))).toBe(
        'brian took back what the AI cleared.',
      )
      expect(stepLine(step({ action: 'suggestion_dismissed', by: 'brian' }))).toBe(
        'brian turned down the AI’s suggestion to clear it.',
      )
      expect(
        stepLine(step({ action: 'suggestion_confirmed', by: 'brian', verdict: 'low_priority' })),
      ).toBe('brian cleared this as low priority (91% sure).')
    })
  })
})
