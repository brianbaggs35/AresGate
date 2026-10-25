import * as client from '@/api/client'
import { fetchStorage, setRetention } from '@/api/storage'

const opnsense = {
  source: 'opnsense',
  name: 'OPNsense',
  days: 90,
  effective_days: 90,
  oldest_at: '2026-10-01T00:00:00Z',
}

describe('storage', () => {
  it('reads how many events each integration has stored', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({
      default_days: 30,
      sources: [{ ...opnsense, events: 120 }],
    })

    await expect(fetchStorage('events')).resolves.toEqual({
      default_days: 30,
      sources: [{ ...opnsense, count: 120 }],
    })
    expect(get).toHaveBeenCalledWith('/events/storage')
  })

  it('reads how many readings each integration has stored, which the API calls samples', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({
      default_days: 14,
      sources: [{ ...opnsense, days: null, effective_days: 14, oldest_at: null, samples: 0 }],
    })

    const storage = await fetchStorage('metrics')

    expect(get).toHaveBeenCalledWith('/metrics/storage')
    expect(storage.sources).toEqual([
      { ...opnsense, days: null, effective_days: 14, oldest_at: null, count: 0 },
    ])
    expect(storage.sources[0]).not.toHaveProperty('samples')
  })

  it('sets how long an integration keeps its events, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ ...opnsense, events: 7 })

    await expect(setRetention('events', 'opnsense', 90, 'a-token')).resolves.toEqual({
      ...opnsense,
      count: 7,
    })
    expect(put).toHaveBeenCalledWith('/events/storage/opnsense', { days: 90 }, 'a-token')
  })

  it('goes back to the default with null', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ ...opnsense, samples: 3 })

    const changed = await setRetention('metrics', 'opnsense', null, 'a-token')

    expect(put).toHaveBeenCalledWith('/metrics/storage/opnsense', { days: null }, 'a-token')
    expect(changed.count).toBe(3)
  })

  it('keeps a name from changing the address it sets', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ ...opnsense, events: 0 })

    await setRetention('events', 'a/b', 7, 'a-token')

    expect(put).toHaveBeenCalledWith('/events/storage/a%2Fb', { days: 7 }, 'a-token')
  })
})
