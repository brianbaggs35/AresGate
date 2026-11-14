import { useAnswerProgress } from '@/chatProgress'

describe('useAnswerProgress', () => {
  it('collects what the answer looked at and what it has written', () => {
    const progress = useAnswerProgress()

    progress.follow({ kind: 'looked', lookup: { tool: 'alerts', summary: '3 alerts' } })
    progress.follow({ kind: 'wrote', text: 'Nothing ' })
    progress.follow({ kind: 'wrote', text: 'to do.' })

    expect(progress.looked.value).toEqual([{ tool: 'alerts', summary: '3 alerts' }])
    expect(progress.writing.value).toBe('Nothing to do.')
  })

  it('forgets what was written when it was not the answer after all, and keeps the lookups', () => {
    const progress = useAnswerProgress()
    progress.follow({ kind: 'looked', lookup: { tool: 'alerts', summary: '3 alerts' } })
    progress.follow({ kind: 'wrote', text: 'Hmm' })

    progress.follow({ kind: 'dropped' })

    expect(progress.writing.value).toBe('')
    expect(progress.looked.value).toHaveLength(1)
  })

  it('starts again', () => {
    const progress = useAnswerProgress()
    progress.follow({ kind: 'looked', lookup: { tool: 'alerts', summary: '3 alerts' } })
    progress.follow({ kind: 'wrote', text: 'Hmm' })

    progress.reset()

    expect(progress.looked.value).toEqual([])
    expect(progress.writing.value).toBe('')
  })
})
