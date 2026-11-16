import * as client from '@/api/client'
import { confirmCleared, fetchCleared, fetchClearedCounts, takeBackCleared } from '@/api/aiCleared'
import { clearedPage } from '@/test/cleared'

const PICKS = [{ kind: 'cleared' as const, id: 3 }]

describe('AI cleared API', () => {
  it('asks for a list, a page at a time', async () => {
    const answer = clearedPage()
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchCleared('cleared')).resolves.toBe(answer)
    await fetchCleared('waiting', 5, 10)

    expect(get).toHaveBeenNthCalledWith(1, '/ai/cleared?state=cleared&limit=20&offset=0')
    expect(get).toHaveBeenNthCalledWith(2, '/ai/cleared?state=waiting&limit=5&offset=10')
  })

  it('asks how many there are', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ waiting: 1, cleared: 2 })

    await expect(fetchClearedCounts()).resolves.toEqual({ waiting: 1, cleared: 2 })
    expect(get).toHaveBeenCalledWith('/ai/cleared/summary')
  })

  it('confirms, as another verdict if asked', async () => {
    const answer = { done: 1, skipped: 0, counts: { waiting: 0, cleared: 0 } }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(answer)

    await expect(confirmCleared(PICKS, 'a-token')).resolves.toBe(answer)
    await confirmCleared(PICKS, 'a-token', 'low_priority')

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/ai/cleared/confirm',
      { items: PICKS, verdict: undefined },
      'a-token',
    )
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/ai/cleared/confirm',
      { items: PICKS, verdict: 'low_priority' },
      'a-token',
    )
  })

  it('takes back', async () => {
    const answer = { done: 1, skipped: 1, counts: { waiting: 0, cleared: 0 } }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(answer)

    await expect(takeBackCleared(PICKS, 'a-token')).resolves.toBe(answer)
    expect(post).toHaveBeenCalledWith('/ai/cleared/take-back', { items: PICKS }, 'a-token')
  })
})
