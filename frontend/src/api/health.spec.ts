import * as client from '@/api/client'
import { fetchHealth } from '@/api/health'

describe('fetchHealth', () => {
  it('returns what the API reports', async () => {
    vi.spyOn(client, 'apiGet').mockResolvedValue({ status: 'ok', database: 'ok' })
    await expect(fetchHealth()).resolves.toEqual({ status: 'ok', database: 'ok' })
  })

  it('treats a 503 as a degraded install, not a failure', async () => {
    vi.spyOn(client, 'apiGet').mockRejectedValue(new client.ApiError(503, 'down'))
    await expect(fetchHealth()).resolves.toEqual({ status: 'degraded', database: 'unavailable' })
  })

  it('passes other failures on', async () => {
    vi.spyOn(client, 'apiGet').mockRejectedValue(new client.ApiError(0, 'offline', 'offline'))
    await expect(fetchHealth()).rejects.toMatchObject({ code: 'offline' })
  })
})
