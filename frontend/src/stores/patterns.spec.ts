import { createPinia, setActivePinia } from 'pinia'

import { PATTERNS_STORAGE_KEY, usePatternsStore } from '@/stores/patterns'

describe('patterns store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('is off until the owner turns it on', () => {
    expect(usePatternsStore().preference).toBe('off')
  })

  it('restores a saved choice, and ignores one that is not a choice', () => {
    localStorage.setItem(PATTERNS_STORAGE_KEY, 'on')
    expect(usePatternsStore().preference).toBe('on')

    setActivePinia(createPinia())
    localStorage.setItem(PATTERNS_STORAGE_KEY, 'loud')
    expect(usePatternsStore().preference).toBe('off')
  })

  it('saves a new choice', () => {
    const store = usePatternsStore()

    store.setPreference('on')

    expect(store.preference).toBe('on')
    expect(localStorage.getItem(PATTERNS_STORAGE_KEY)).toBe('on')
  })
})
