import type {
  Clearing,
  ClearingCeiling,
  ClearingDraft,
  ClearingKind,
  ClearingMode,
  ClearingPreview,
} from '@/api/aiClearing'

/** What each mode comes to, in words. */
export const MODE_WORDS: Record<ClearingMode, { title: string; words: string }> = {
  off: {
    title: 'Off',
    words:
      'The AI clears nothing and marks nothing. It still reads incidents and gives its opinion.',
  },
  suggest: {
    title: 'Suggest, then confirm',
    words:
      'The AI marks an incident that looks like a false positive and waits for your tap. Nothing is cleared until you say so.',
  },
  automatic: {
    title: 'Automatic',
    words:
      'The AI gives the verdict itself, says why on the incident and in the audit log, and you can take any of it back.',
  },
}

/** What each kind of reading is. */
export const KIND_WORDS: Record<ClearingKind, { title: string; words: string }> = {
  noise: { title: 'Noise', words: 'Background traffic that means nothing.' },
  probe: { title: 'Probes', words: 'Scans and knocks that found nothing.' },
  unclear: { title: 'Unclear', words: 'It could not tell, and thinks it is nothing.' },
}

/** What each ceiling lets the AI clear. */
export const CEILING_WORDS: Record<ClearingCeiling, string> = {
  low: 'Only low and informational incidents.',
  medium: 'Up to medium. High and critical are left to you.',
  high: 'Up to high. Critical is always left to you.',
}

/** The draft of what is kept: every setting that saving changes. */
export function draftOf(kept: Clearing): ClearingDraft {
  return {
    mode: kept.mode,
    minimum: kept.minimum,
    kinds: [...kept.kinds],
    sources: [...kept.sources],
    ceiling: kept.ceiling,
    daily_cap: kept.daily_cap,
  }
}

/** Whether two drafts are the same settings, whatever order the lists are in. */
export function sameDraft(a: ClearingDraft, b: ClearingDraft): boolean {
  const same = (x: readonly string[], y: readonly string[]) =>
    x.length === y.length && [...x].sort().join() === [...y].sort().join()
  return (
    a.mode === b.mode &&
    a.minimum === b.minimum &&
    a.ceiling === b.ceiling &&
    a.daily_cap === b.daily_cap &&
    same(a.kinds, b.kinds) &&
    same(a.sources, b.sources)
  )
}

/** What the preview says, in a sentence. */
export function previewSentence(found: ClearingPreview): string {
  const days = `${found.days.toString()} days`
  if (found.read === 0) return `The AI has not read any incidents in the last ${days} yet.`
  const read = `${found.read.toString()} ${found.read === 1 ? 'incident' : 'incidents'}`
  if (found.would_clear === 0) {
    return `Of the ${read} the AI read in the last ${days}, these settings would have cleared none.`
  }
  return `Of the ${read} the AI read in the last ${days}, these settings would have cleared ${found.would_clear.toString()}.`
}
