import * as client from '@/api/client'
import {
  MAX_BULK,
  changeVerdict,
  fetchVerdicts,
  giveVerdict,
  inBatches,
  removeVerdict,
  takeBackVerdicts,
} from '@/api/verdicts'

describe('verdicts', () => {
  it('lists them, the one given last first', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [{ id: 3 }, { id: 1 }] })

    await expect(fetchVerdicts()).resolves.toEqual([{ id: 3 }, { id: 1 }])
    expect(get).toHaveBeenCalledWith('/verdicts')
  })

  it('gives one, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 4 })
    const request = { verdict: 'threat', address: '93.184.216.34', note: 'seen it before' } as const

    await expect(giveVerdict(request, 'a-token')).resolves.toEqual({ id: 4 })
    expect(post).toHaveBeenCalledWith('/verdicts', request, 'a-token')
  })

  it('changes one, with the sign-in token', async () => {
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue({ id: 4 })

    await expect(
      changeVerdict(4, { verdict: 'low_priority', note: null }, 'a-token'),
    ).resolves.toEqual({
      id: 4,
    })
    expect(patch).toHaveBeenCalledWith(
      '/verdicts/4',
      { verdict: 'low_priority', note: null },
      'a-token',
    )
  })

  it('takes one back, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeVerdict(4, 'a-token')

    expect(remove).toHaveBeenCalledWith('/verdicts/4', 'a-token')
  })

  it('takes many back in one request, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ done: 2, skipped: 1 })

    await expect(takeBackVerdicts([4, 5, 6], 'a-token')).resolves.toEqual({ done: 2, skipped: 1 })
    expect(post).toHaveBeenCalledWith('/verdicts/take-back', { ids: [4, 5, 6] }, 'a-token')
  })

  it('changes more than a request takes in batches, and adds up how it went', async () => {
    const ids = Array.from({ length: MAX_BULK * 2 + 5 }, (_, index) => index + 1)
    const change = vi.fn().mockResolvedValue({ done: 3, skipped: 1 })

    await expect(inBatches(ids, change)).resolves.toEqual({ done: 9, skipped: 3 })

    expect(change.mock.calls.map(([batch]) => (batch as number[]).length)).toEqual([
      MAX_BULK,
      MAX_BULK,
      5,
    ])
  })

  it('changes nothing for no ids', async () => {
    const change = vi.fn()

    await expect(inBatches([], change)).resolves.toEqual({ done: 0, skipped: 0 })
    expect(change).not.toHaveBeenCalled()
  })
})
