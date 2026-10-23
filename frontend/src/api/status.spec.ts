import * as client from '@/api/client'
import { fetchStatus } from '@/api/status'

describe('fetchStatus', () => {
  it('asks the API for the report', async () => {
    const report = { diagnostics: 'AresGate diagnostics' }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(report)
    await expect(fetchStatus()).resolves.toBe(report)
    expect(get).toHaveBeenCalledWith('/status')
  })
})
