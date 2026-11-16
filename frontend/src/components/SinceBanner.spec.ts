import { flushPromises } from '@vue/test-utils'

import * as sinceApi from '@/api/since'
import SinceBanner from '@/components/SinceBanner.vue'
import { mountWithPlugins } from '@/test/mount'

function news(over: Partial<sinceApi.Since> = {}): sinceApi.Since {
  return {
    since: '2026-11-16T08:00:00Z',
    incidents: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    cleared_by_ai: 0,
    new_devices: 0,
    total: 0,
    ...over,
  }
}

async function open(found: sinceApi.Since | Error) {
  const fetch = vi.spyOn(sinceApi, 'fetchSince')
  if (found instanceof Error) fetch.mockRejectedValue(found)
  else fetch.mockResolvedValue(found)
  const seen = vi.spyOn(sinceApi, 'markSeen').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(SinceBanner, { signedIn: 'admin' })
  await flushPromises()
  return { ...mounted, seen }
}

describe('SinceBanner', () => {
  it('says nothing when nothing is new', async () => {
    const { wrapper } = await open(news())

    expect(wrapper.find('[data-test="since"]').exists()).toBe(false)
  })

  it('says nothing when it cannot tell what is new', async () => {
    const { wrapper } = await open(new Error('down'))

    expect(wrapper.find('[data-test="since"]').exists()).toBe(false)
  })

  it('names the new incidents by how serious, worst first, and opens what it counted', async () => {
    const { wrapper } = await open(
      news({ incidents: { critical: 0, high: 2, medium: 0, low: 1200, info: 0 }, total: 1202 }),
    )

    const link = wrapper.find('[data-test="since-incidents"]')
    expect(link.text()).toBe('1,202 new incidents (2 high, 1,200 low)')
    const href = link.attributes('href') as string
    expect(href).toContain('/incidents?')
    expect(decodeURIComponent(href)).toContain('began:"2026-11-16T08:00:00Z"')
    expect(href).toContain('view=all')
  })

  it('speaks of one incident, one device and what the AI cleared', async () => {
    const { wrapper } = await open(
      news({
        incidents: { critical: 1, high: 0, medium: 0, low: 0, info: 0 },
        cleared_by_ai: 4,
        new_devices: 1,
        total: 6,
      }),
    )

    expect(wrapper.find('[data-test="since-incidents"]').text()).toBe('1 new incident (1 critical)')
    expect(wrapper.find('[data-test="since-cleared"]').text()).toBe('4 cleared by the AI')
    expect(wrapper.find('[data-test="since-cleared"]').attributes('href')).toBe('/cleared')
    expect(wrapper.find('[data-test="since-devices"]').text()).toBe('1 new device')
    expect(wrapper.find('[data-test="since-devices"]').attributes('href')).toBe('/assets?new=1')
  })

  it('speaks of several devices', async () => {
    const { wrapper } = await open(news({ new_devices: 3, total: 3 }))

    expect(wrapper.find('[data-test="since-devices"]').text()).toBe('3 new devices')
    expect(wrapper.find('[data-test="since-incidents"]').exists()).toBe(false)
  })

  it('counts as looked at when dismissed, and goes away', async () => {
    const { wrapper, seen } = await open(news({ new_devices: 2, total: 2 }))

    await wrapper.find('[data-test="since-dismiss"]').trigger('click')
    await flushPromises()

    expect(seen).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="since"]').exists()).toBe(false)
    wrapper.unmount()
    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('goes away even when the server cannot be told, and says nothing more', async () => {
    const { wrapper, seen } = await open(news({ new_devices: 2, total: 2 }))
    seen.mockRejectedValue(new Error('down'))

    await wrapper.find('[data-test="since-dismiss"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="since"]').exists()).toBe(false)
  })

  it('counts leaving the page as looking at what it said', async () => {
    const { wrapper, seen } = await open(news({ new_devices: 2, total: 2 }))

    wrapper.unmount()
    await flushPromises()

    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('does not count leaving when it said nothing, and copes when telling fails', async () => {
    const quiet = await open(news())
    quiet.wrapper.unmount()
    expect(quiet.seen).not.toHaveBeenCalled()

    const loud = await open(news({ new_devices: 1, total: 1 }))
    loud.seen.mockRejectedValue(new Error('down'))
    loud.wrapper.unmount()
    await flushPromises()
    expect(loud.seen).toHaveBeenCalledTimes(1)
  })
})
