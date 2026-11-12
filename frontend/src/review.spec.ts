import {
  REVIEW,
  REVIEW_LISTS,
  REVIEW_MODE,
  agreePercent,
  autoFromSentence,
  standingLine,
} from '@/review'
import type { ReviewStanding } from '@/api/review'

function standing(changes: Partial<ReviewStanding> = {}): ReviewStanding {
  return {
    agreed: 0,
    disagreed: 0,
    rate: null,
    trusted: false,
    trust_after: 20,
    trust_rate: 0.95,
    ...changes,
  }
}

describe('review words', () => {
  it('names every state, its meaning and its mode', () => {
    expect(Object.keys(REVIEW)).toEqual(['pending', 'auto', 'agreed', 'disagreed'])
    expect(REVIEW_LISTS.map((each) => each.key)).toEqual(['waiting', 'decided', 'answered'])
    expect(Object.keys(REVIEW_MODE)).toEqual(['all', 'uncertain', 'auto'])
  })

  it('rounds how often the owner agreed, and has nothing before they answer', () => {
    expect(agreePercent(standing())).toBeNull()
    expect(agreePercent(standing({ rate: 0.876 }))).toBe(88)
  })

  it('invites the first answers', () => {
    expect(standingLine(standing())).toBe(
      'Answer a few decisions and AresGate learns how much to trust the AI.',
    )
  })

  it('counts the answers still needed, in the singular too', () => {
    const few = standing({ agreed: 8, disagreed: 2, rate: 0.8 })
    expect(standingLine(few)).toBe(
      'You agreed with 8 of 10 decisions (80%). 10 more answers and AresGate can tell whether it has earned your trust.',
    )
    const almost = standing({ agreed: 18, disagreed: 1, rate: 18 / 19 })
    expect(standingLine(almost)).toContain('1 more answer and')
  })

  it('says it has not earned trust yet once enough were answered', () => {
    const line = standingLine(standing({ agreed: 15, disagreed: 10, rate: 0.6 }))
    expect(line).toBe('You agreed with 15 of 25 decisions (60%). It earns your trust at 95%.')
  })

  it('says it has earned trust', () => {
    const line = standingLine(standing({ agreed: 24, disagreed: 1, rate: 0.96, trusted: true }))
    expect(line).toContain('That is enough to let it decide on its own')
  })

  it('says what a level of sureness does', () => {
    expect(autoFromSentence(90)).toBe(
      'A decision it is 90% sure of or more counts at once. Anything less waits for you.',
    )
  })
})
