import { VSelect, VTextField } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as threatsApi from '@/api/threats'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { family } from '@/test/threats'
import KindsView from '@/views/KindsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(page: threatsApi.FamilyPage | Error | null = null, route = '/threats/kinds') {
  const fetchIt = vi.spyOn(threatsApi, 'fetchFamilies')
  const first = page ?? { total: 1, items: [family()] }
  if (first instanceof Error) fetchIt.mockRejectedValue(first)
  else fetchIt.mockResolvedValue(first)
  const mounted = await mountWithPlugins(KindsView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const selects = () => mounted.wrapper.findAllComponents(VSelect)
  return { ...mounted, fetchIt, find, selects }
}

describe('KindsView', () => {
  it('asks for the first page of kinds, with no narrowing', async () => {
    const { fetchIt, find } = await open()

    expect(fetchIt).toHaveBeenCalledWith({ limit: 20, offset: 0 })
    expect(find('kinds-total').text()).toBe('1 kind')
    expect(find('kinds-list').findAll('[data-test="family-card"]')).toHaveLength(1)
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(threatsApi, 'fetchFamilies').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(KindsView, {
      signedIn: 'admin',
      route: '/threats/kinds',
    })

    expect(wrapper.find('[data-test="kinds-loading"]').exists()).toBe(true)
  })

  it('drops the failure of a question that a newer one has taken the place of', async () => {
    let fail: (reason: Error) => void = () => {}
    const fetchIt = vi.spyOn(threatsApi, 'fetchFamilies')
    fetchIt.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    fetchIt.mockResolvedValue({ total: 1, items: [family()] })
    const { router, wrapper } = await mountWithPlugins(KindsView, {
      signedIn: 'admin',
      withApp: true,
      route: '/threats/kinds',
    })
    await router.replace({ query: { lane: 'threat' } })
    await flushPromises()

    fail(offline())
    await flushPromises()

    expect(wrapper.find('[data-test="kinds-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="kinds-stale"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="kinds-list"]').exists()).toBe(true)
  })

  it('leads back to the threats', async () => {
    const { find } = await open()

    expect(find('back').attributes('href')).toBe('/threats')
  })

  it('narrows the list by what is in the address of the page', async () => {
    const { fetchIt, selects, wrapper } = await open(
      null,
      '/threats/kinds?lane=threat&judged=waiting&q=ssh',
    )

    expect(fetchIt).toHaveBeenCalledWith({
      lane: 'threat',
      judged: 'waiting',
      q: 'ssh',
      limit: 20,
      offset: 0,
    })
    expect(selects()[0]?.props('modelValue')).toBe('threat')
    expect(selects()[1]?.props('modelValue')).toBe('waiting')
    expect(wrapper.findComponent(VTextField).props('modelValue')).toBe('ssh')
  })

  it('ignores what in the address is not one of the choices', async () => {
    const { fetchIt } = await open(null, '/threats/kinds?lane=other&judged=maybe&q[]=a')

    expect(fetchIt).toHaveBeenCalledWith({ limit: 20, offset: 0 })
  })

  it('puts a choice in the address and asks again', async () => {
    const { fetchIt, selects, router } = await open()

    selects()[0]?.vm.$emit('update:modelValue', 'suspect')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({ lane: 'suspect' })
    })
    selects()[1]?.vm.$emit('update:modelValue', 'ai')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({ lane: 'suspect', judged: 'ai' })
    })
    expect(fetchIt).toHaveBeenLastCalledWith({
      lane: 'suspect',
      judged: 'ai',
      limit: 20,
      offset: 0,
    })

    selects()[0]?.vm.$emit('update:modelValue', null)
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({ judged: 'ai' })
    })
  })

  it('searches a moment after the last word is typed', async () => {
    const { fetchIt, wrapper, router } = await open()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const field = wrapper.findComponent(VTextField)

      field.vm.$emit('update:modelValue', 'ss')
      field.vm.$emit('update:modelValue', ' ssh ')
      await vi.advanceTimersByTimeAsync(299)
      expect(fetchIt).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(1)

      await vi.waitFor(() => {
        expect(router.currentRoute.value.query).toEqual({ q: 'ssh' })
      })
      await vi.waitFor(() => {
        expect(fetchIt).toHaveBeenLastCalledWith({ q: 'ssh', limit: 20, offset: 0 })
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('searches for nothing when the field is cleared', async () => {
    const { wrapper, router } = await open(null, '/threats/kinds?q=ssh')
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      wrapper.findComponent(VTextField).vm.$emit('update:modelValue', null)
      await vi.advanceTimersByTimeAsync(300)

      await vi.waitFor(() => {
        expect(router.currentRoute.value.query).toEqual({})
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('says when nothing matches', async () => {
    const { find } = await open({ total: 0, items: [] })

    expect(find('kinds-empty').exists()).toBe(true)
    expect(find('kinds-total').text()).toBe('0 kinds')
  })

  it('shows more, a page at a time, until all are shown', async () => {
    const { fetchIt, find, wrapper } = await open({
      total: 3,
      items: [family({ id: 1 }), family({ id: 2 })],
    })
    expect(find('kinds-more').text()).toBe('Show more (1 left)')
    fetchIt.mockResolvedValue({ total: 3, items: [family({ id: 3 })] })

    await find('kinds-more').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith({ limit: 20, offset: 2 })
    expect(wrapper.findAll('[data-test="family-card"]')).toHaveLength(3)
    expect(find('kinds-more').exists()).toBe(false)
  })

  it('says why more could not be shown, and keeps what it has', async () => {
    const { fetchIt, find, wrapper } = await open({ total: 3, items: [family()] })
    fetchIt.mockRejectedValue(offline())

    await find('kinds-more').trigger('click')
    await flushPromises()

    expect(find('kinds-more-error').text()).toBe("Can't reach AresGate.")
    expect(wrapper.findAll('[data-test="family-card"]')).toHaveLength(1)
  })

  it('says why it could not load, and tries again on request', async () => {
    const { fetchIt, find } = await open(offline())

    expect(find('kinds-error').text()).toContain("Can't reach AresGate.")

    fetchIt.mockResolvedValue({ total: 1, items: [family()] })
    await find('retry').trigger('click')
    await flushPromises()

    expect(find('kinds-error').exists()).toBe(false)
    expect(find('kinds-list').exists()).toBe(true)
  })

  it('keeps what it has when a new question fails, and says so', async () => {
    const { fetchIt, find, router } = await open()
    fetchIt.mockRejectedValue(offline())

    await router.replace({ query: { lane: 'threat' } })
    await flushPromises()

    expect(find('kinds-stale').text()).toContain("Can't reach AresGate.")
    expect(find('kinds-list').exists()).toBe(true)

    fetchIt.mockResolvedValue({ total: 1, items: [family()] })
    await router.replace({ query: { lane: 'suspect' } })
    await flushPromises()
    expect(find('kinds-stale').exists()).toBe(false)
  })

  it('drops the answer to an older question', async () => {
    const { fetchIt, router, find } = await open()
    let late: (page: threatsApi.FamilyPage) => void = () => {}
    fetchIt.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
    fetchIt.mockResolvedValueOnce({ total: 1, items: [family({ id: 2, label: 'Newer' })] })

    await router.replace({ query: { lane: 'threat' } })
    await router.replace({ query: { lane: 'suspect' } })
    await flushPromises()
    late({ total: 1, items: [family({ id: 1, label: 'Older' })] })
    await flushPromises()

    expect(find('kinds-list').text()).toContain('Newer')
    expect(find('kinds-list').text()).not.toContain('Older')
  })
})
