import * as client from '@/api/client'
import { changeView, deleteView, fetchViews, saveView } from '@/api/views'
import { kept } from '@/test/views'

describe('views', () => {
  it('lists what is kept for every page', async () => {
    const items = [kept()]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items })

    await expect(fetchViews()).resolves.toBe(items)
    expect(get).toHaveBeenCalledWith('/views')
  })

  it('keeps a view under a name, with the security token', async () => {
    const answer = kept()
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(answer)

    await expect(saveView('assets', 'New', { new: 'true' }, true, 'token')).resolves.toBe(answer)
    expect(post).toHaveBeenCalledWith(
      '/views',
      { page: 'assets', name: 'New', query: { new: 'true' }, default: true },
      'token',
    )
  })

  it('changes one by its id', async () => {
    const answer = kept({ name: 'Other' })
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue(answer)

    await expect(changeView(4, { name: 'Other' }, 'token')).resolves.toBe(answer)
    expect(patch).toHaveBeenCalledWith('/views/4', { name: 'Other' }, 'token')
  })

  it('forgets one by its id', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await deleteView(4, 'token')

    expect(remove).toHaveBeenCalledWith('/views/4', 'token')
  })
})
