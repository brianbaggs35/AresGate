import { createPinia, setActivePinia } from 'pinia'

import { ApiError } from '@/api/client'
import * as viewsApi from '@/api/views'
import { useSessionStore } from '@/stores/session'
import { useViewsStore } from '@/stores/views'
import { kept } from '@/test/views'

function store() {
  setActivePinia(createPinia())
  useSessionStore().$patch({ known: true, username: 'admin', csrfToken: 'token' })
  return useViewsStore()
}

describe('the views store', () => {
  it('asks once and keeps them by page and then name', async () => {
    const fetch = vi
      .spyOn(viewsApi, 'fetchViews')
      .mockResolvedValue([
        kept({ id: 3, page: 'incidents', name: 'b' }),
        kept({ id: 1, page: 'assets', name: 'Z' }),
        kept({ id: 2, page: 'incidents', name: 'A' }),
      ])
    const views = store()

    await Promise.all([views.load(), views.load()])
    await views.load()

    expect(fetch).toHaveBeenCalledTimes(1)
    expect(views.loaded).toBe(true)
    expect(views.of('incidents').map((view) => view.name)).toEqual(['b', 'A'])
    expect(views.of('assets').map((view) => view.name)).toEqual(['Z'])
  })

  it('says why it could not ask, and asks again next time', async () => {
    const fetch = vi
      .spyOn(viewsApi, 'fetchViews')
      .mockRejectedValueOnce(new ApiError(0, "Can't reach AresGate.", 'offline'))
      .mockResolvedValue([])
    const views = store()

    await views.load()

    expect(views.failure).toBe("Can't reach AresGate.")
    expect(views.loaded).toBe(false)

    await views.load()

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(views.failure).toBeNull()
    expect(views.loaded).toBe(true)
  })

  it('finds the one a page opens on', async () => {
    vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue([
      kept({ id: 1, name: 'First' }),
      kept({ id: 2, name: 'Second', is_default: true }),
    ])
    const views = store()
    await views.load()

    expect(views.defaultOf('incidents')?.name).toBe('Second')
    expect(views.defaultOf('assets')).toBeUndefined()
  })

  it('keeps a view saved, in its place, and takes the default from the page’s others', async () => {
    vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue([
      kept({ id: 1, name: 'First', is_default: true }),
      kept({ id: 5, page: 'assets', name: 'Elsewhere', is_default: true }),
    ])
    const save = vi
      .spyOn(viewsApi, 'saveView')
      .mockResolvedValue(kept({ id: 2, name: 'Second', is_default: true }))
    const views = store()
    await views.load()

    const saved = await views.save('incidents', 'Second', { view: 'all' }, true)

    expect(save).toHaveBeenCalledWith('incidents', 'Second', { view: 'all' }, true, 'token')
    expect(saved.id).toBe(2)
    expect(views.of('incidents').map((view) => [view.name, view.is_default])).toEqual([
      ['First', false],
      ['Second', true],
    ])
    expect(views.defaultOf('assets')?.name).toBe('Elsewhere')
  })

  it('replaces one that is saved again', async () => {
    vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue([kept({ id: 1, query: { a: '1' } })])
    vi.spyOn(viewsApi, 'saveView').mockResolvedValue(kept({ id: 1, query: { a: '2' } }))
    const views = store()
    await views.load()

    await views.save('incidents', 'Needs a look', { a: '2' })

    expect(views.items.map((view) => view.query)).toEqual([{ a: '2' }])
  })

  it('renames, makes default and forgets', async () => {
    vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue([
      kept({ id: 1 }),
      kept({ id: 2, name: 'B' }),
    ])
    const change = vi.spyOn(viewsApi, 'changeView')
    const forget = vi.spyOn(viewsApi, 'deleteView').mockResolvedValue(undefined)
    const views = store()
    await views.load()
    const [first, second] = views.items as [viewsApi.SavedView, viewsApi.SavedView]

    change.mockResolvedValueOnce({ ...first, name: 'Renamed' })
    await views.rename(first, 'Renamed')
    change.mockResolvedValueOnce({ ...second, is_default: true })
    await views.setDefault(second, true)
    await views.remove(first)

    expect(change).toHaveBeenNthCalledWith(1, 1, { name: 'Renamed' }, 'token')
    expect(change).toHaveBeenNthCalledWith(2, 2, { default: true }, 'token')
    expect(forget).toHaveBeenCalledWith(1, 'token')
    expect(views.items.map((view) => [view.name, view.is_default])).toEqual([['B', true]])
  })
})
