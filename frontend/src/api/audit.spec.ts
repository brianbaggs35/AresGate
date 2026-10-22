import { fetchRecentActivity } from '@/api/audit'
import * as client from '@/api/client'

describe('fetchRecentActivity', () => {
  it('returns the newest events, as many as asked for', async () => {
    const events = [
      { id: 2, action: 'auth.logout' },
      { id: 1, action: 'auth.login_succeeded' },
    ]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ events, next_before: null })
    await expect(fetchRecentActivity(20)).resolves.toEqual(events)
    expect(get).toHaveBeenCalledWith('/audit/events?limit=20')
  })
})
