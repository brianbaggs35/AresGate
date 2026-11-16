import { createPinia, setActivePinia } from 'pinia'

import {
  GROUPING_STORAGE_KEY,
  LAYOUT_STORAGE_KEY,
  useIncidentLayoutStore,
} from '@/stores/incident-layout'

describe('incident layout store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('is cards, with nothing grouped, until the owner chooses otherwise', () => {
    const store = useIncidentLayoutStore()

    expect(store.layout).toBe('cards')
    expect(store.grouping).toBe('none')
  })

  it('restores what was chosen', () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, 'table')
    localStorage.setItem(GROUPING_STORAGE_KEY, 'address')

    const store = useIncidentLayoutStore()

    expect(store.layout).toBe('table')
    expect(store.grouping).toBe('address')
  })

  it('ignores a saved value that is not a choice', () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, 'wall')
    localStorage.setItem(GROUPING_STORAGE_KEY, 'planet')

    const store = useIncidentLayoutStore()

    expect(store.layout).toBe('cards')
    expect(store.grouping).toBe('none')
  })

  it('saves new choices', () => {
    const store = useIncidentLayoutStore()

    store.setLayout('table')
    store.setGrouping('address')

    expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toBe('table')
    expect(localStorage.getItem(GROUPING_STORAGE_KEY)).toBe('address')
  })

  it('still applies a choice when storage cannot be written', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    const store = useIncidentLayoutStore()

    store.setLayout('table')

    expect(store.layout).toBe('table')
  })
})
