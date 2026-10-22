import { createPinia, setActivePinia } from 'pinia'

import * as healthApi from '@/api/health'
import { useHealthStore } from '@/stores/health'

describe('health store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads health', async () => {
    vi.spyOn(healthApi, 'fetchHealth').mockResolvedValue({ status: 'ok', database: 'ok' })
    const store = useHealthStore()
    const pending = store.refresh()
    expect(store.loading).toBe(true)
    await pending
    expect(store.loading).toBe(false)
    expect(store.health).toEqual({ status: 'ok', database: 'ok' })
    expect(store.error).toBeNull()
  })

  it('records an error message and clears stale data', async () => {
    const store = useHealthStore()
    store.health = { status: 'ok', database: 'ok' }
    vi.spyOn(healthApi, 'fetchHealth').mockRejectedValue(new Error('offline'))
    await store.refresh()
    expect(store.health).toBeNull()
    expect(store.error).toBe('offline')
    expect(store.loading).toBe(false)
  })
})
