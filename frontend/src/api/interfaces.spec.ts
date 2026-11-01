import * as client from '@/api/client'
import {
  changeInterface,
  createInterface,
  discoverFeeds,
  fetchInterfaces,
  fetchOverview,
  placeFeed,
  removeInterface,
  type InterfaceRequest,
} from '@/api/interfaces'

describe('interfaces', () => {
  it('lists them with the feeds on them', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ interfaces: [] })

    await expect(fetchInterfaces()).resolves.toEqual({ interfaces: [] })
    expect(get).toHaveBeenCalledWith('/interfaces')
  })

  it('asks what each has been doing for a window', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ stats: [] })

    await fetchOverview('7d')

    expect(get).toHaveBeenCalledWith('/interfaces/overview?window=7d')
  })

  it('makes one, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 3 })
    const request: InterfaceRequest = { name: 'Guests', role: 'guest', feeds: [4] }

    await expect(createInterface(request, 'a-token')).resolves.toEqual({ id: 3 })
    expect(post).toHaveBeenCalledWith('/interfaces', request, 'a-token')
  })

  it('changes one, with the sign-in token', async () => {
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue({ id: 3 })

    await changeInterface(3, { name: 'Visitors' }, 'a-token')

    expect(patch).toHaveBeenCalledWith('/interfaces/3', { name: 'Visitors' }, 'a-token')
  })

  it('removes one, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeInterface(3, 'a-token')

    expect(remove).toHaveBeenCalledWith('/interfaces/3', 'a-token')
  })

  it('places a feed, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ id: 9 })

    await placeFeed(9, { interface_id: 3 }, 'a-token')

    expect(put).toHaveBeenCalledWith('/interfaces/feeds/9', { interface_id: 3 }, 'a-token')
  })

  it('looks for feeds, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ new: 2 })

    await expect(discoverFeeds('a-token')).resolves.toEqual({ new: 2 })
    expect(post).toHaveBeenCalledWith('/interfaces/discover', undefined, 'a-token')
  })
})
