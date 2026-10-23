import * as client from '@/api/client'
import { fetchCollectors } from '@/api/collectors'

describe('collectors', () => {
  it('reads the worker and every collector', async () => {
    const report = { worker: { state: 'running' }, collectors: [] }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(report)
    await expect(fetchCollectors()).resolves.toBe(report)
    expect(get).toHaveBeenCalledWith('/collectors')
  })

  it('can ask for only those of one integration', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})
    await fetchCollectors('wazuh')
    expect(get).toHaveBeenCalledWith('/collectors?integration=wazuh')
  })

  it('keeps a name from changing the address it asks for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})
    await fetchCollectors('a&b=c')
    expect(get).toHaveBeenCalledWith('/collectors?integration=a%26b%3Dc')
  })
})
