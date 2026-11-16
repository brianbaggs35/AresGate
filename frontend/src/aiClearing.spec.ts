import type { ClearingDraft } from '@/api/aiClearing'
import { draftOf, previewSentence, sameDraft } from '@/aiClearing'
import { clearing } from '@/test/aiClearing'

describe('the clearing settings', () => {
  it('makes a draft of what is kept that does not change what is kept', () => {
    const kept = clearing()
    const draft = draftOf(kept)

    draft.kinds.pop()
    draft.sources.push('wazuh')

    expect(kept.kinds).toHaveLength(3)
    expect(kept.sources).toEqual([])
    expect(Object.keys(draftOf(kept)).sort()).toEqual([
      'ceiling',
      'daily_cap',
      'kinds',
      'minimum',
      'mode',
      'sources',
    ])
  })

  it('knows when two drafts are the same, whatever order the lists are in', () => {
    const a = draftOf(clearing({ sources: ['ntopng', 'wazuh'], kinds: ['noise', 'probe'] }))

    expect(sameDraft(a, { ...a, sources: ['wazuh', 'ntopng'], kinds: ['probe', 'noise'] })).toBe(
      true,
    )
  })

  it.each([
    ['mode', { mode: 'off' }],
    ['minimum', { minimum: 70 }],
    ['ceiling', { ceiling: 'high' }],
    ['daily_cap', { daily_cap: 1 }],
    ['kinds', { kinds: ['noise'] }],
    ['sources', { sources: ['wazuh'] }],
    ['more sources', { sources: ['wazuh', 'ntopng', 'x'] }],
  ] as [string, Partial<ClearingDraft>][])('knows when %s differs', (_, change) => {
    const a = draftOf(clearing())

    expect(sameDraft(a, { ...a, ...change })).toBe(false)
  })

  it('says what it would have cleared', () => {
    expect(previewSentence({ days: 7, read: 0, would_clear: 0 })).toBe(
      'The AI has not read any incidents in the last 7 days yet.',
    )
    expect(previewSentence({ days: 7, read: 1, would_clear: 0 })).toBe(
      'Of the 1 incident the AI read in the last 7 days, these settings would have cleared none.',
    )
    expect(previewSentence({ days: 7, read: 12, would_clear: 4 })).toBe(
      'Of the 12 incidents the AI read in the last 7 days, these settings would have cleared 4.',
    )
  })
})
