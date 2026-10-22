import * as healthApi from '@/api/health'
import HomeView from '@/views/HomeView.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const status = (wrapper: { find: (selector: string) => { text: () => string } }, name: string) =>
  wrapper.find(`[data-test="${name}-status"]`).text()

describe('HomeView', () => {
  it('shows the API and database as healthy', async () => {
    vi.spyOn(healthApi, 'fetchHealth').mockResolvedValue({ status: 'ok', database: 'ok' })
    const { wrapper } = await mountWithPlugins(HomeView)
    await flushPromises()
    expect(status(wrapper, 'api')).toBe('API: Running')
    expect(status(wrapper, 'database')).toBe('Database: Connected')
  })

  it('shows an unavailable database', async () => {
    vi.spyOn(healthApi, 'fetchHealth').mockResolvedValue({
      status: 'degraded',
      database: 'unavailable',
    })
    const { wrapper } = await mountWithPlugins(HomeView)
    await flushPromises()
    expect(status(wrapper, 'api')).toBe('API: Running')
    expect(status(wrapper, 'database')).toBe('Database: Unavailable')
  })

  it('shows an unreachable API', async () => {
    vi.spyOn(healthApi, 'fetchHealth').mockRejectedValue(new Error('offline'))
    const { wrapper } = await mountWithPlugins(HomeView)
    await flushPromises()
    expect(status(wrapper, 'api')).toBe('API: Unreachable')
    expect(status(wrapper, 'database')).toBe('Database: Unknown')
  })

  it('says it is checking until the API answers', async () => {
    vi.spyOn(healthApi, 'fetchHealth').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(HomeView)
    expect(status(wrapper, 'api')).toBe('API: Checking…')
  })

  it('checks again on request', async () => {
    const fetchHealth = vi
      .spyOn(healthApi, 'fetchHealth')
      .mockResolvedValue({ status: 'ok', database: 'ok' })
    const { wrapper } = await mountWithPlugins(HomeView)
    await flushPromises()
    await wrapper.find('[data-test="refresh"]').trigger('click')
    await flushPromises()
    expect(fetchHealth).toHaveBeenCalledTimes(2)
  })
})
