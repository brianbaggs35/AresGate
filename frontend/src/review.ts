import { Check, Clock3, Sparkles, X } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { ReviewList, ReviewMode, ReviewStanding, ReviewState } from '@/api/review'

type Icon = NonNullable<IconProps['icon']>

/** What each state of a review looks like: a word, an icon and a theme color, never a color
 * alone. */
export const REVIEW: Readonly<
  Record<ReviewState, { label: string; icon: Icon; color: string; meaning: string }>
> = {
  pending: {
    label: 'Waiting for you',
    icon: Clock3,
    color: 'warning',
    meaning: 'The AI has decided, and it is waiting for you to look at it.',
  },
  auto: {
    label: 'Decided for you',
    icon: Sparkles,
    color: 'primary',
    meaning: 'The AI decided and it counted at once, as you allowed.',
  },
  agreed: {
    label: 'You agreed',
    icon: Check,
    color: 'success',
    meaning: 'You agreed with the AI, so what it decided counts.',
  },
  disagreed: {
    label: 'You disagreed',
    icon: X,
    color: 'error',
    meaning: 'You disagreed with the AI, so what it decided does not count.',
  },
}

/** The lists of the Review page, in order. */
export const REVIEW_LISTS: readonly { key: ReviewList; label: string; empty: string }[] = [
  {
    key: 'waiting',
    label: 'Waiting',
    empty: 'Nothing is waiting for you. When the AI decides something, it is here to look at.',
  },
  {
    key: 'decided',
    label: 'Decided for you',
    empty: 'The AI has not decided anything on its own yet.',
  },
  {
    key: 'answered',
    label: 'Answered',
    empty: 'You have not answered anything yet.',
  },
]

/** How much of what the AI decides waits for the owner, said in words. */
export const REVIEW_MODE: Readonly<Record<ReviewMode, { label: string; meaning: string }>> = {
  all: {
    label: 'Everything waits for me',
    meaning:
      'The AI can still raise an alarm on its own, but whatever it would set aside waits until you agree.',
  },
  uncertain: {
    label: 'Only what the AI is unsure of',
    meaning: 'What it is very sure of counts at once, and the rest waits for you.',
  },
  auto: {
    label: 'The AI decides on its own',
    meaning: 'Everything it decides counts at once. You can still look at it and disagree.',
  },
}

/** How often the owner has agreed, as a whole percent, or null until they have answered. */
export function agreePercent(standing: ReviewStanding): number | null {
  return standing.rate === null ? null : Math.round(standing.rate * 100)
}

/** What the owner's record with the AI says, in a line. */
export function standingLine(standing: ReviewStanding): string {
  const answered = standing.agreed + standing.disagreed
  const percent = agreePercent(standing)
  if (percent === null)
    return 'Answer a few decisions and AresGate learns how much to trust the AI.'
  const lead = `You agreed with ${standing.agreed.toString()} of ${answered.toString()} decisions (${percent.toString()}%).`
  if (standing.trusted) return `${lead} That is enough to let it decide on its own, if you want.`
  if (answered < standing.trust_after) {
    const more = standing.trust_after - answered
    return `${lead} ${more.toString()} more ${more === 1 ? 'answer' : 'answers'} and AresGate can tell whether it has earned your trust.`
  }
  return `${lead} It earns your trust at ${Math.round(standing.trust_rate * 100).toString()}%.`
}

/** The sentence for how sure the AI has to be, with `uncertain`. */
export function autoFromSentence(autoFrom: number): string {
  return `A decision it is ${autoFrom.toString()}% sure of or more counts at once. Anything less waits for you.`
}
