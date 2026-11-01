import * as client from '@/api/client'
import {
  fetchUsage,
  fetchUsageCall,
  fetchUsageCalls,
  saveLevel,
  saveLimits,
  timeZone,
  usageCsvUrl,
} from '@/api/aiUsage'

describe('AI usage API', () => {
  beforeEach(() => {
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(
      () => ({ resolvedOptions: () => ({ timeZone: 'America/Halifax' }) }) as Intl.DateTimeFormat,
    )
  })

  it('knows the time zone it is in', () => {
    expect(timeZone()).toBe('America/Halifax')
  })

  it('asks for the range in its own time zone', async () => {
    const answer = { range: '30d' }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchUsage('30d')).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/ai/usage?range=30d&timezone=America%2FHalifax')
  })

  it('asks for a page of the calls', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [] })

    await fetchUsageCalls('7d', 25, 50)

    expect(get).toHaveBeenCalledWith(
      '/ai/usage/calls?range=7d&timezone=America%2FHalifax&limit=25&offset=50',
    )
  })

  it('asks for one call', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 3 })

    await fetchUsageCall(3)

    expect(get).toHaveBeenCalledWith('/ai/usage/calls/3')
  })

  it('says where the spreadsheet is', () => {
    expect(usageCsvUrl('90d')).toBe('/api/ai/usage.csv?range=90d&timezone=America%2FHalifax')
  })

  it('keeps the limits with the security token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue([])

    await saveLimits({ daily: '2.50', monthly: null }, 'a-token')

    expect(put).toHaveBeenCalledWith('/ai/limits', { daily: '2.50', monthly: null }, 'a-token')
  })

  it('keeps the level with the security token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ level: 'high' })

    await expect(saveLevel('high', 'a-token')).resolves.toEqual({ level: 'high' })

    expect(put).toHaveBeenCalledWith('/ai/level', { level: 'high' }, 'a-token')
  })
})
