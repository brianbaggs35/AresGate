import { createPinia, setActivePinia } from 'pinia'

import { MENU_STORAGE_KEY, useNavigationStore } from '@/stores/navigation'

describe('navigation store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('leaves the width to the screen until a choice is made', () => {
    expect(useNavigationStore().width).toBeNull()
  })

  it('restores a saved choice', () => {
    localStorage.setItem(MENU_STORAGE_KEY, 'rail')
    expect(useNavigationStore().width).toBe('rail')
  })

  it('ignores an invalid saved value', () => {
    localStorage.setItem(MENU_STORAGE_KEY, 'huge')
    expect(useNavigationStore().width).toBeNull()
  })

  it('saves a new choice', () => {
    const store = useNavigationStore()
    store.setWidth('full')
    expect(store.width).toBe('full')
    expect(localStorage.getItem(MENU_STORAGE_KEY)).toBe('full')
  })
})
