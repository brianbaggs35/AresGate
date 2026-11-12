import * as client from '@/api/client'
import {
  agreeWith,
  answerDecision,
  fetchReview,
  fetchReviewSettings,
  fetchWaiting,
  saveReviewSettings,
} from '@/api/review'

describe('review api', () => {
  it('asks for a list with how many to show', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await expect(fetchReview('waiting', 20)).resolves.toEqual({ total: 0 })
    expect(get).toHaveBeenCalledWith('/review?state=waiting&limit=20')
  })

  it('asks for a later part of a list', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchReview('answered', 20, 40)
    expect(get).toHaveBeenCalledWith('/review?state=answered&limit=20&offset=40')
  })

  it('asks how many wait', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ waiting: 4 })

    await expect(fetchWaiting()).resolves.toEqual({ waiting: 4 })
    expect(get).toHaveBeenCalledWith('/review/summary')
  })

  it('answers a decision with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 7 })

    await answerDecision('family', 7, 'disagree', 'It is mine', true, 'a-token')

    expect(post).toHaveBeenCalledWith(
      '/review/family/7',
      { answer: 'disagree', reason: 'It is mine', keep_kind: true },
      'a-token',
    )
  })

  it('agrees with several at once', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ agreed: 2 })
    const items = [
      { subject: 'family' as const, id: 1 },
      { subject: 'incident' as const, id: 2 },
    ]

    await expect(agreeWith(items, 'a-token')).resolves.toEqual({ agreed: 2 })
    expect(post).toHaveBeenCalledWith('/review/agree', { items }, 'a-token')
  })

  it('reads and keeps the settings', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ mode: 'all' })
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ mode: 'auto' })
    const draft = { mode: 'auto' as const, auto_from: 90, learn: false }

    await fetchReviewSettings()
    await saveReviewSettings(draft, 'a-token')

    expect(get).toHaveBeenCalledWith('/review/settings')
    expect(put).toHaveBeenCalledWith('/review/settings', draft, 'a-token')
  })
})
