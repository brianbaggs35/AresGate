import { ApiError } from '@/api/client'
import BarChart from '@/charts/BarChart.vue'
import * as flowApi from '@/api/flow'
import { flow } from '@/test/flow'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import FlowView from '@/views/FlowView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open({
  route = '/flow',
  answer = flow(),
}: { route?: string; answer?: flowApi.Flow | Error } = {}) {
  const fetchFlow = vi.spyOn(flowApi, 'fetchFlow')
  if (answer instanceof Error) fetchFlow.mockRejectedValue(answer)
  else fetchFlow.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(FlowView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchFlow, find, text, choose }
}

describe('FlowView', () => {
  it('asks for the last day of everything, and says what it found', async () => {
    const { fetchFlow, text, wrapper } = await open()

    expect(fetchFlow).toHaveBeenCalledWith(24, 'all')
    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('Network Flow')
    expect(text('stat-events')).toBe('11')
    expect(text('stat-blocked')).toBe('5 (45%)')
    expect(text('flow-caption')).toBe('Every connection the firewall wrote down.')
    expect(wrapper.find('[data-test="flow-chart"]').exists()).toBe(true)
    expect(text('updated')).toContain('Updated')
  })

  it('shows a skeleton until the first answer arrives', async () => {
    vi.spyOn(flowApi, 'fetchFlow').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(FlowView, {
      signedIn: 'admin',
      withApp: true,
      route: '/flow',
    })

    expect(wrapper.find('[data-test="flow-loading"]').exists()).toBe(true)
  })

  it('says why it could not read, and tries again', async () => {
    const { find, fetchFlow, choose } = await open({ answer: offline() })

    expect(find('flow-error').exists()).toBe(true)
    fetchFlow.mockResolvedValue(flow())
    await choose(() => find('flow-error').find('button').trigger('click'))

    expect(find('flow-error').exists()).toBe(false)
    expect(find('flow-chart').exists()).toBe(true)
  })

  it('keeps what it has, and says so, when a later ask fails', async () => {
    const { find, fetchFlow, choose } = await open()
    fetchFlow.mockRejectedValue(offline())

    await choose(() => find('refresh').trigger('click'))

    expect(find('flow-stale').text()).toContain("Can't reach AresGate.")
    expect(find('flow-chart').exists()).toBe(true)
  })

  describe('the window and the direction', () => {
    it('come from the address of the page, and ignore what is not a choice', async () => {
      const { fetchFlow } = await open({ route: '/flow?hours=6&direction=incoming' })
      expect(fetchFlow).toHaveBeenCalledWith(6, 'incoming')

      const other = await open({ route: '/flow?hours=5&direction=sideways' })
      expect(other.fetchFlow).toHaveBeenLastCalledWith(24, 'all')
    })

    it('ask again when another is chosen, and say so in the address', async () => {
      const { fetchFlow, find, choose, router } = await open()

      await choose(() => find('window-168').trigger('click'))
      expect(fetchFlow).toHaveBeenLastCalledWith(168, 'all')
      expect(router.currentRoute.value.query).toEqual({ hours: '168' })

      await choose(() => find('direction-outgoing').trigger('click'))
      expect(fetchFlow).toHaveBeenLastCalledWith(168, 'outgoing')
      expect(router.currentRoute.value.query).toEqual({ hours: '168', direction: 'outgoing' })

      await choose(() => find('window-24').trigger('click'))
      await choose(() => find('direction-all').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('say what a direction means', async () => {
      const { find } = await open()

      expect(find('direction-incoming').attributes('title')).toBe('From the Internet to the home')
    })

    it('drop the answer to an older ask', async () => {
      const { fetchFlow, find, choose, text } = await open()
      let late: (value: flowApi.Flow) => void = () => undefined
      fetchFlow.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchFlow.mockResolvedValueOnce(flow({ events: 99, blocked: 0 }))

      await choose(() => find('window-1').trigger('click'))
      await choose(() => find('window-6').trigger('click'))
      late(flow({ events: 5, blocked: 0 }))
      await flushPromises()

      expect(text('stat-events')).toBe('99')
    })
  })

  describe('picking a block', () => {
    it('opens its details beside the picture, which can be closed', async () => {
      const { find, choose } = await open()
      expect(find('flow-detail').exists()).toBe(false)

      await choose(() => find('flow-node-source:8.8.8.8').trigger('click'))
      expect(find('detail-name').text()).toBe('8.8.8.8')

      await choose(() => find('detail-close').trigger('click'))
      expect(find('flow-detail').exists()).toBe(false)
    })

    it('is let go when the window changes', async () => {
      const { find, choose } = await open()
      await choose(() => find('flow-node-source:8.8.8.8').trigger('click'))

      await choose(() => find('window-6').trigger('click'))

      expect(find('flow-detail').exists()).toBe(false)
    })

    it('is let go when what was picked is no longer there', async () => {
      const { find, choose, fetchFlow } = await open()
      await choose(() => find('flow-node-source:8.8.8.8').trigger('click'))
      fetchFlow.mockResolvedValue(flow({ nodes: [], links: [] }))

      await choose(() => find('refresh').trigger('click'))

      expect(find('flow-detail').exists()).toBe(false)
    })
  })

  describe('the timeline', () => {
    it('is a bar for each stretch, with the allowed and the refused', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('[data-test="flow-timeline"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Connections over time')
    })

    it('leads to the logs of the stretch of time that was picked', async () => {
      const { wrapper, router, choose } = await open()
      const bars = wrapper.findComponent(BarChart)

      await choose(() => bars.vm.$emit('select', 23))

      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('logs')
      })
      const query = router.currentRoute.value.query.q as string
      expect(query).toMatch(/^kind:firewall since:\S+ before:\S+$/)
    })

    it('does nothing for a bar that is not there', async () => {
      const { wrapper, router, choose } = await open()
      const bars = wrapper.findComponent(BarChart)

      await choose(() => bars.vm.$emit('select', 99))

      expect(router.currentRoute.value.name).toBe('flow')
    })
  })

  it('asks again every half minute while the page is open, leaving what is on screen alone', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { fetchFlow, find } = await open()
      fetchFlow.mockReturnValue(new Promise(() => {}))

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(fetchFlow).toHaveBeenCalledTimes(2)
      expect(find('flow-chart').exists()).toBe(true)
      expect(find('flow-loading').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('ignores the failure of an ask that is no longer the one made', async () => {
    const { fetchFlow, find, choose } = await open()
    let fail: (error: Error) => void = () => undefined
    fetchFlow.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    fetchFlow.mockResolvedValueOnce(flow())

    await choose(() => find('window-1').trigger('click'))
    await choose(() => find('window-6').trigger('click'))
    fail(offline())
    await flushPromises()

    expect(find('flow-stale').exists()).toBe(false)
  })

  it('says when there was more than it reads', async () => {
    const { text } = await open({ answer: flow({ capped: true }) })

    expect(text('flow-caption')).toContain('the busiest of what was seen')
  })
})
