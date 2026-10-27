import * as client from '@/api/client'
import { deleteSavedSearch, fetchSavedSearches, saveSearch } from '@/api/searches'
import { saved } from '@/test/searches'

describe('searches', () => {
  it('lists what is kept for a page', async () => {
    const kept = [saved()]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: kept })

    await expect(fetchSavedSearches('logs')).resolves.toBe(kept)
    expect(get).toHaveBeenCalledWith('/searches?scope=logs')
  })

  it('keeps a search under a name, with the security token', async () => {
    const answer = saved()
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(answer)

    await expect(saveSearch('incidents', 'Scans', 'severity>=high', 'token')).resolves.toBe(answer)
    expect(post).toHaveBeenCalledWith(
      '/searches',
      { scope: 'incidents', name: 'Scans', query: 'severity>=high' },
      'token',
    )
  })

  it('forgets one by its id', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await deleteSavedSearch(4, 'token')

    expect(remove).toHaveBeenCalledWith('/searches/4', 'token')
  })
})
