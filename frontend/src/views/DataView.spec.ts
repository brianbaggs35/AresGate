import * as storageApi from '@/api/storage'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import DataView from '@/views/DataView.vue'

describe('DataView', () => {
  it('has a card for the events and another for the measurements', async () => {
    const fetchIt = vi
      .spyOn(storageApi, 'fetchStorage')
      .mockResolvedValue({ default_days: 30, sources: [] })
    const { wrapper } = await mountWithPlugins(DataView, {
      route: '/settings/data',
      signedIn: 'admin',
    })
    await flushPromises()

    expect(wrapper.find('[data-test="events-retention-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="metrics-retention-card"]').exists()).toBe(true)
    expect(fetchIt.mock.calls.map(([kind]) => kind).sort()).toEqual(['events', 'metrics'])
  })

  it('shows one card when the other cannot load', async () => {
    vi.spyOn(storageApi, 'fetchStorage').mockImplementation((kind) =>
      kind === 'events'
        ? Promise.reject(new Error("Can't reach AresGate."))
        : Promise.resolve({ default_days: 30, sources: [] }),
    )
    const { wrapper } = await mountWithPlugins(DataView, {
      route: '/settings/data',
      signedIn: 'admin',
    })
    await flushPromises()

    expect(wrapper.find('[data-test="retention-error"]').exists()).toBe(true)
    expect(
      wrapper.find('[data-test="metrics-retention-card"] [data-test="retention-list"]').exists(),
    ).toBe(true)
  })
})
