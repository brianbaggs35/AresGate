import {
  addDestination,
  changeDestination,
  fetchDestinations,
  removeDestination,
  testDestination,
} from '@/api/alerts'
import * as client from '@/api/client'

describe('alerts', () => {
  it('lists the destinations', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [{ id: 3 }] })

    await expect(fetchDestinations()).resolves.toEqual({ items: [{ id: 3 }] })
    expect(get).toHaveBeenCalledWith('/alerts/destinations')
  })

  it('adds one, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 4 })
    const add = { name: 'Security', url: 'https://discord.com/api/webhooks/1/x' }

    await expect(addDestination(add, 'a-token')).resolves.toEqual({ id: 4 })
    expect(post).toHaveBeenCalledWith('/alerts/destinations', add, 'a-token')
  })

  it('changes one, with the sign-in token', async () => {
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue({ id: 4 })

    await expect(changeDestination(4, { enabled: false }, 'a-token')).resolves.toEqual({ id: 4 })
    expect(patch).toHaveBeenCalledWith('/alerts/destinations/4', { enabled: false }, 'a-token')
  })

  it('removes one, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeDestination(4, 'a-token')

    expect(remove).toHaveBeenCalledWith('/alerts/destinations/4', 'a-token')
  })

  it('sends a test message, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })

    await expect(testDestination(4, 'a-token')).resolves.toEqual({ ok: true })
    expect(post).toHaveBeenCalledWith('/alerts/destinations/4/test', undefined, 'a-token')
  })
})
