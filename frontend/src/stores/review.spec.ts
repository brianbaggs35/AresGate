import { createPinia, setActivePinia } from 'pinia'

import * as reviewApi from '@/api/review'
import { useReviewStore } from '@/stores/review'

describe('review store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts with nothing waiting', () => {
    expect(useReviewStore().waiting).toBe(0)
  })

  it('asks how many wait', async () => {
    vi.spyOn(reviewApi, 'fetchWaiting').mockResolvedValue({ waiting: 6 })
    const store = useReviewStore()

    await store.refresh()

    expect(store.waiting).toBe(6)
  })

  it('keeps the count it has when it cannot ask', async () => {
    const store = useReviewStore()
    store.set(3)
    vi.spyOn(reviewApi, 'fetchWaiting').mockRejectedValue(new Error('offline'))

    await store.refresh()

    expect(store.waiting).toBe(3)
  })
})
