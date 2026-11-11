import * as client from '@/api/client'
import {
  callFamily,
  fetchChain,
  fetchChains,
  fetchFamilies,
  fetchFamily,
  fetchOverview,
  judgeFamily,
} from '@/api/threats'

describe('threats', () => {
  it('asks for the overview of a window', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ funnel: {} })

    await expect(fetchOverview('7d')).resolves.toEqual({ funnel: {} })
    expect(get).toHaveBeenCalledWith('/threats/overview?window=7d')
  })

  it('lists the kinds of incident when asked for nothing in particular', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchFamilies()

    expect(get).toHaveBeenCalledWith('/threats/families')
  })

  it('narrows the kinds by what is asked for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchFamilies({ lane: 'threat', judged: 'waiting', q: 'scan', limit: 10, offset: 20 })

    expect(get).toHaveBeenCalledWith(
      '/threats/families?lane=threat&judged=waiting&q=scan&limit=10&offset=20',
    )
  })

  it('leaves out what means everything', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchFamilies({ q: '', offset: 0, limit: 5 })

    expect(get).toHaveBeenCalledWith('/threats/families?limit=5')
  })

  it('reads one kind', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 3 })

    await expect(fetchFamily(3)).resolves.toEqual({ id: 3 })
    expect(get).toHaveBeenCalledWith('/threats/families/3')
  })

  it('says what to do with a kind, or takes the word back, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ id: 3 })

    await callFamily(3, 'background', 'a-token')
    await callFamily(3, null, 'a-token')

    expect(put).toHaveBeenNthCalledWith(
      1,
      '/threats/families/3/call',
      { call: 'background' },
      'a-token',
    )
    expect(put).toHaveBeenNthCalledWith(2, '/threats/families/3/call', { call: null }, 'a-token')
  })

  it('has the AI judge a kind, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })

    await expect(judgeFamily(3, 'a-token')).resolves.toEqual({ ok: true })
    expect(post).toHaveBeenCalledWith('/threats/families/3/judge', {}, 'a-token')
  })

  it('lists the chains when asked for nothing in particular', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchChains()

    expect(get).toHaveBeenCalledWith('/threats/chains')
  })

  it('narrows the chains by what is asked for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchChains({ confirmed: false, limit: 6, offset: 12 })

    expect(get).toHaveBeenCalledWith('/threats/chains?confirmed=false&limit=6&offset=12')
  })

  it('reads one chain', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 4 })

    await expect(fetchChain(4)).resolves.toEqual({ id: 4 })
    expect(get).toHaveBeenCalledWith('/threats/chains/4')
  })
})
