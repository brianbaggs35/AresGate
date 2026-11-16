import { createPinia, setActivePinia } from 'pinia'

import { DENSITY_STORAGE_KEY, useDensityStore } from '@/stores/density'

describe('density store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('is roomy until the owner chooses otherwise', () => {
    expect(useDensityStore().preference).toBe('comfortable')
  })

  it('restores a saved choice', () => {
    localStorage.setItem(DENSITY_STORAGE_KEY, 'compact')
    expect(useDensityStore().preference).toBe('compact')
  })

  it('ignores a saved value that is not a choice', () => {
    localStorage.setItem(DENSITY_STORAGE_KEY, 'tiny')
    expect(useDensityStore().preference).toBe('comfortable')
  })

  it('saves a new choice', () => {
    const store = useDensityStore()

    store.setPreference('compact')

    expect(store.preference).toBe('compact')
    expect(localStorage.getItem(DENSITY_STORAGE_KEY)).toBe('compact')
  })

  it('still applies a choice when storage cannot be written', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    const store = useDensityStore()

    store.setPreference('compact')

    expect(store.preference).toBe('compact')
  })
})
