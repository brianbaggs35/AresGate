import * as client from '@/api/client'
import { changeVerdict, fetchVerdicts, giveVerdict, removeVerdict } from '@/api/verdicts'

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
})
