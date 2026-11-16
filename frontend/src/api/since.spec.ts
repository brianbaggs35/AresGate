import * as client from '@/api/client'
import { fetchSince, markSeen } from '@/api/since'

describe('since API', () => {
  it('asks what is new', async () => {
    const answer = {
      since: null,
      incidents: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
      cleared_by_ai: 0,
      new_devices: 0,
      total: 0,
    }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchSince()).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/dashboard/since')
  })

  it('says it has looked', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)

    await markSeen('a-token')

    expect(post).toHaveBeenCalledWith('/dashboard/seen', undefined, 'a-token')
  })
})
