import * as client from '@/api/client'
import { fetchDashboard, WINDOWS } from '@/api/dashboard'

describe('dashboard', () => {
  it('asks for the window it is given', async () => {
    const answer = { window: { key: '7d' } }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchDashboard('7d')).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/dashboard?window=7d')
  })

  it('offers the windows from the shortest, each with what comes before it', () => {
    expect(WINDOWS.map(({ key, before }) => [key, before])).toEqual([
      ['24h', 'the day before'],
      ['7d', 'the week before'],
    ])
  })
})
