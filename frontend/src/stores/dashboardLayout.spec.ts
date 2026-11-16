import { createPinia, setActivePinia } from 'pinia'

import * as layoutApi from '@/api/dashboardLayout'
import { DEFAULT_PLACES, type Place } from '@/dashboardLayout'
import { useDashboardLayoutStore } from '@/stores/dashboardLayout'

const place = (id: Place['id'], hidden = false): Place => ({ id, size: 'half', hidden })

const presets = [
  { key: 'overview', title: 'Overview', description: 'All of it.', widgets: [] },
  {
    key: 'quiet',
    title: 'Quiet',
    description: 'Only what needs you.',
    widgets: [{ id: 'needs_you', size: 'full' as const, hidden: false }],
  },
]

describe('dashboard layout store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts as the default dashboard, so the page never waits', () => {
    const store = useDashboardLayoutStore()

    expect(store.places).toEqual(DEFAULT_PLACES)
    expect(store.preset).toBe('overview')
    expect(store.presets).toEqual([])
    expect(store.error).toBeNull()
  })

  it('reads the layout the account has', async () => {
    vi.spyOn(layoutApi, 'fetchLayout').mockResolvedValue({
      preset: null,
      widgets: [{ id: 'latest', size: 'full', hidden: true }],
      presets,
    })
    const store = useDashboardLayoutStore()

    await store.load()

    expect(store.places[0]).toEqual({ id: 'latest', size: 'full', hidden: true })
    expect(store.preset).toBeNull()
    expect(store.presets).toEqual(presets)
    expect(store.shown.map((shown) => shown.id)).not.toContain('latest')
  })

  it('keeps the default, and says why, when it cannot read the layout', async () => {
    vi.spyOn(layoutApi, 'fetchLayout').mockRejectedValue(new Error('offline'))
    const store = useDashboardLayoutStore()

    await store.load()

    expect(store.places).toEqual(DEFAULT_PLACES)
    expect(store.error).toBe('offline')
  })

  it('shows a change at once and saves it with the sign-in token', async () => {
    const save = vi.spyOn(layoutApi, 'saveLayout').mockResolvedValue({
      preset: null,
      widgets: [],
      presets: [],
    })
    const store = useDashboardLayoutStore()
    const next = [place('traffic', true), place('alerts')]

    const saving = store.save(next)

    expect(store.places).toEqual(next)
    expect(store.saving).toBe(true)
    await saving
    expect(store.saving).toBe(false)
    expect(store.preset).toBeNull()
    expect(save).toHaveBeenCalledWith(
      {
        preset: null,
        widgets: [
          { id: 'traffic', size: 'half', hidden: true },
          { id: 'alerts', size: 'half', hidden: false },
        ],
      },
      '',
    )
    expect(store.places[0]).not.toBe(next[0])
  })

  it('takes the old layout back, and says why, when saving fails', async () => {
    vi.spyOn(layoutApi, 'saveLayout').mockRejectedValue(new Error('no'))
    const store = useDashboardLayoutStore()
    const before = store.places

    await store.save([place('traffic')])

    expect(store.places).toBe(before)
    expect(store.preset).toBe('overview')
    expect(store.error).toBe('no')
    expect(store.saving).toBe(false)
  })

  it('starts over from a preset, and notes which', async () => {
    vi.spyOn(layoutApi, 'fetchLayout').mockResolvedValue({
      preset: 'overview',
      widgets: [],
      presets,
    })
    const save = vi
      .spyOn(layoutApi, 'saveLayout')
      .mockResolvedValue({ preset: 'quiet', widgets: [], presets })
    const store = useDashboardLayoutStore()
    await store.load()

    await store.apply('quiet')

    expect(store.preset).toBe('quiet')
    expect(store.places[0]).toEqual({ id: 'needs_you', size: 'full', hidden: false })
    expect(save.mock.calls[0]![0].preset).toBe('quiet')
  })

  it('does nothing for a preset it has not got', async () => {
    const save = vi.spyOn(layoutApi, 'saveLayout')

    await useDashboardLayoutStore().apply('missing')

    expect(save).not.toHaveBeenCalled()
  })

  it('puts the first preset back', async () => {
    const reset = vi.spyOn(layoutApi, 'resetLayout').mockResolvedValue(undefined)
    const store = useDashboardLayoutStore()
    store.places = [place('traffic')]
    store.preset = null

    await store.reset()

    expect(reset).toHaveBeenCalledWith('')
    expect(store.places).toEqual(DEFAULT_PLACES)
    expect(store.preset).toBe('overview')
    expect(store.saving).toBe(false)
  })

  it('leaves the layout as it is, and says why, when it cannot put it back', async () => {
    vi.spyOn(layoutApi, 'resetLayout').mockRejectedValue(new Error('no'))
    const store = useDashboardLayoutStore()
    store.preset = null

    await store.reset()

    expect(store.preset).toBeNull()
    expect(store.error).toBe('no')
  })
})
