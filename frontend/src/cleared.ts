import type { ClearedCounts, ClearedState } from '@/api/aiCleared'
import type { ClearingStep } from '@/api/incidents'
import { VERDICT } from '@/verdicts'

/** The two lists of the page for what the AI cleared, and what each says when it is empty. */
export const CLEARED_LISTS: readonly { key: ClearedState; label: string; empty: string }[] = [
  {
    key: 'waiting',
    label: 'Waiting for you',
    empty:
      'Nothing is waiting. What the AI thinks is a false positive, and is not allowed to clear by itself, shows here for your word.',
  },
  {
    key: 'cleared',
    label: 'Cleared by the AI',
    empty:
      'The AI has not cleared anything you have not confirmed. Everything it clears by itself shows here until you confirm or take it back.',
  },
]

/** How the page says which of its lists is which, with how many are in each. */
export function countOf(counts: ClearedCounts, key: ClearedState): number {
  return counts[key]
}

const plural = (count: number, one: string, many: string) =>
  `${count.toString()} ${count === 1 ? one : many}`

/** What the dashboard says of what the AI cleared, or null when there is nothing to say. What it
 * cleared always shows, so that it is never done unseen. */
export function nudgeText(counts: ClearedCounts): string | null {
  const parts: string[] = []
  if (counts.cleared > 0) {
    parts.push(
      `${plural(counts.cleared, 'incident', 'incidents')} cleared by the AI that ${counts.cleared === 1 ? 'is' : 'are'} not confirmed`,
    )
  }
  if (counts.waiting > 0) {
    parts.push(
      `${plural(counts.waiting, 'incident', 'incidents')} the AI suggests clearing ${counts.waiting === 1 ? 'waits' : 'wait'} for you`,
    )
  }
  return parts.length ? `${parts.join(', and ')}.` : null
}

const WHAT: Readonly<Record<ClearingStep['action'], string>> = {
  cleared: 'cleared this',
  confirmed: 'confirmed it as the AI cleared it',
  taken_back: 'took back what the AI cleared',
  suggestion_confirmed: 'cleared this',
  suggestion_dismissed: 'turned down the AI’s suggestion to clear it',
}

/** One step of an incident's clearing, as a sentence: "The AI cleared this as not suspicious
 * (91% sure)." */
export function stepLine(step: ClearingStep): string {
  const who = step.by === 'the AI' ? 'The AI' : step.by
  const sure = step.confidence === null ? '' : ` (${step.confidence.toString()}% sure)`
  const verdict = step.verdict ? ` as ${VERDICT[step.verdict].label.toLowerCase()}` : ''
  const clears = step.action === 'cleared' || step.action === 'suggestion_confirmed'
  return `${who} ${WHAT[step.action]}${clears ? verdict : ''}${clears ? sure : ''}.`
}
