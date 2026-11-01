import * as usageApi from '@/api/aiUsage'
import { ApiError } from '@/api/client'
import AiCallDialog from '@/components/AiCallDialog.vue'
import AiCallsTable from '@/components/AiCallsTable.vue'
import { callDetail, callPage, usageCall } from '@/test/aiUsage'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(first: usageApi.UsageCallPage | Error = callPage(3)) {
  const fetchCalls = vi.spyOn(usageApi, 'fetchUsageCalls')
  if (first instanceof Error) fetchCalls.mockRejectedValue(first)
  else fetchCalls.mockResolvedValue(first)
  vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(callDetail())
  const mounted = await mountWithPlugins(AiCallsTable, {
    signedIn: 'admin',
    props: { range: '7d', refreshed: 0 },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetchCalls, find }
}

describe('AiCallsTable', () => {
  it('lists the requests, newest first as the API gave them', async () => {
    const { wrapper, fetchCalls } = await show()

    expect(fetchCalls).toHaveBeenCalledWith('7d', 25, 0)
    const rows = wrapper.findAll('[data-test="call"]')
    expect(rows).toHaveLength(3)
    expect(rows[0]?.text()).toContain('Reading incidents, incident 1')
    expect(rows[0]?.text()).toContain('Claude Haiku 5.5')
    expect(rows[0]?.text()).toContain('1.5K tokens'.replace('1.5K', '1,500'))
    expect(rows[0]?.text()).toContain('$0.0015')
  })

  it('says what went wrong with a request that failed, and what it is about when it is about nothing', async () => {
    const { wrapper } = await show({
      total: 1,
      items: [
        usageCall({
          ok: false,
          error: "It didn't answer in time.",
          about: null,
          cost_micros: null,
        }),
      ],
    })

    expect(wrapper.find('[data-test="call-failed"]').text()).toBe(
      "Failed: It didn't answer in time.",
    )
    expect(wrapper.find('[data-test="call-use"]').text()).toBe('Reading incidents')
    expect(wrapper.find('[data-test="call"]').text()).toContain('–')
  })

  it('shows the rest a page at a time', async () => {
    const { wrapper, fetchCalls, find } = await show(callPage(25, 30))
    expect(find('calls-more').text()).toBe('Show 5 more')
    fetchCalls.mockResolvedValue(callPage(5, 30, 26))

    await find('calls-more').trigger('click')
    await flushPromises()

    expect(fetchCalls).toHaveBeenLastCalledWith('7d', 25, 25)
    expect(wrapper.findAll('[data-test="call"]')).toHaveLength(30)
    expect(find('calls-more').exists()).toBe(false)
  })

  it('offers no more when all are shown', async () => {
    const { find } = await show(callPage(3))

    expect(find('calls-more').exists()).toBe(false)
  })

  it('shows what a request sent when one is opened', async () => {
    const { wrapper, find } = await show()

    await wrapper.findAll('[data-test="call-open"]')[1]?.trigger('click')
    await flushPromises()

    const dialog = wrapper.findComponent(AiCallDialog)
    expect(dialog.props('callId')).toBe(2)
    expect(dialog.props('modelValue')).toBe(true)
    expect(find('call-open').attributes('aria-label')).toContain(
      'See what was sent: Reading incidents',
    )
  })

  it('hides it again when the dialog is dismissed', async () => {
    const { wrapper } = await show()
    await wrapper.find('[data-test="call-open"]').trigger('click')
    const dialog = wrapper.findComponent(AiCallDialog)

    dialog.vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(dialog.props('modelValue')).toBe(false)
  })

  it('says when there were none', async () => {
    const { find } = await show(callPage(0))

    expect(find('calls-empty').text()).toContain('No requests in this range')
  })

  it('says when they could not be listed, and asks again', async () => {
    const { find, fetchCalls } = await show(offline())
    expect(find('load-error-message').text()).toBe("Can't reach AresGate.")
    fetchCalls.mockResolvedValue(callPage(2))

    await find('calls-retry').trigger('click')
    await flushPromises()

    expect(find('calls-empty').exists()).toBe(false)
    expect(find('call').exists()).toBe(true)
  })

  it('keeps the list when the next page could not be had', async () => {
    const { wrapper, fetchCalls, find } = await show(callPage(25, 30))
    fetchCalls.mockRejectedValue(offline())

    await find('calls-more').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-test="call"]')).toHaveLength(25)
    expect(wrapper.find('[role="alert"]').text()).toBe("Can't reach AresGate.")
  })

  it('shows a placeholder while it asks', async () => {
    vi.spyOn(usageApi, 'fetchUsageCalls').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AiCallsTable, {
      signedIn: 'admin',
      props: { range: '7d', refreshed: 0 },
    })

    expect(wrapper.find('[data-test="calls-loading"]').exists()).toBe(true)
  })

  it('asks again for another range, and again when the page asks again', async () => {
    const { wrapper, fetchCalls } = await show()

    await wrapper.setProps({ range: '90d' })
    await flushPromises()
    await wrapper.setProps({ refreshed: 1 })
    await flushPromises()

    expect(fetchCalls.mock.calls.map(([range]) => range)).toEqual(['7d', '90d', '90d'])
  })

  it('drops the answer to a range it is no longer showing', async () => {
    let answerFirst: (page: usageApi.UsageCallPage) => void = () => {}
    const fetchCalls = vi
      .spyOn(usageApi, 'fetchUsageCalls')
      .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
      .mockResolvedValueOnce(callPage(2, 2, 100))
    const { wrapper } = await mountWithPlugins(AiCallsTable, {
      signedIn: 'admin',
      props: { range: '7d', refreshed: 0 },
    })
    await wrapper.setProps({ range: '30d' })
    await flushPromises()
    answerFirst(callPage(5, 5))
    await flushPromises()

    expect(fetchCalls).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-test="call"]')).toHaveLength(2)
  })

  it('drops the failure of a range it is no longer showing', async () => {
    let failFirst: (error: Error) => void = () => {}
    vi.spyOn(usageApi, 'fetchUsageCalls')
      .mockReturnValueOnce(new Promise((_, reject) => (failFirst = reject)))
      .mockResolvedValueOnce(callPage(2, 2, 100))
    const { wrapper } = await mountWithPlugins(AiCallsTable, {
      signedIn: 'admin',
      props: { range: '7d', refreshed: 0 },
    })
    await wrapper.setProps({ range: '30d' })
    await flushPromises()
    failFirst(offline())
    await flushPromises()

    expect(wrapper.find('[data-test="load-error-message"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="call"]')).toHaveLength(2)
  })
})
