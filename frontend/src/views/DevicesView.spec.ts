import type { VueWrapper } from '@vue/test-utils'
import { VBtnToggle, VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as devicesApi from '@/api/devices'
import AssetSearch from '@/components/AssetSearch.vue'
import DeviceCard from '@/components/DeviceCard.vue'
import { device, devicePage, yours } from '@/test/devices'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import DevicesView from '@/views/DevicesView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

/** Three devices: a laptop of the home, a server it called and a scanner that called in. */
function some() {
  return devicePage([
    yours({ address: '192.168.1.20' }),
    device({ address: '52.1.2.3', name: 'example.test' }),
    device({
      address: '8.8.8.8',
      incoming: 0,
      outgoing: 9,
      incidents: { count: 2, worst: 'critical' },
    }),
  ])
}

interface Options {
  route?: string
  answer?: devicesApi.DevicePage | Error
}

async function open({ route = '/devices', answer = some() }: Options = {}) {
  const fetchDevices = vi.spyOn(devicesApi, 'fetchDevices')
  if (answer instanceof Error) fetchDevices.mockRejectedValue(answer)
  else fetchDevices.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(DevicesView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const addresses = () =>
    mounted.wrapper.findAll('[data-test="device-address"]').map((item) => item.text())
  /** Does what someone does to the filters, and waits for the new address of the page and for the
   * list to be asked for again. */
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchDevices, find, text, addresses, choose }
}

/** The drop-down with this label. */
function select(wrapper: VueWrapper, label: string) {
  return wrapper.findAllComponents(VSelect).find((each) => each.props('label') === label)!
}

function last(fetchDevices: { mock: { calls: unknown[][] } }) {
  return fetchDevices.mock.calls.at(-1)?.[0] as devicesApi.DeviceQuery
}

describe('DevicesView', () => {
  it('asks for the first page, with every scope and no choices', async () => {
    const { fetchDevices } = await open()

    expect(fetchDevices).toHaveBeenCalledTimes(1)
    expect(last(fetchDevices)).toEqual({ flagged: false, sort: 'recent', limit: 30, offset: 0 })
  })

  it('shows a skeleton until the first answer arrives', async () => {
    vi.spyOn(devicesApi, 'fetchDevices').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(DevicesView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="devices-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="device-list"]').exists()).toBe(false)
  })

  it('has a heading, says how many there are and how many are on the Internet', async () => {
    const { wrapper, addresses } = await open()

    expect(wrapper.find('h1').text()).toBe('Devices')
    expect(wrapper.find('[data-test="page-description"]').text()).toBe(
      '3 devices this week, 2 on the Internet.',
    )
    expect(addresses()).toEqual(['192.168.1.20', '52.1.2.3', '8.8.8.8'])
    expect(wrapper.findAllComponents(DeviceCard)).toHaveLength(3)
  })

  it('says "1 device" for one', async () => {
    const { wrapper } = await open({ answer: devicePage([device()]) })

    expect(wrapper.find('[data-test="page-description"]').text()).toBe(
      '1 device this week, 1 on the Internet.',
    )
  })

  it('has a heading for the list so the page can be read by its headings', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('h2').map((heading) => heading.text())).toEqual(['Devices'])
  })

  it('explains what a connection is, and when it read the page', async () => {
    const { text, find } = await open()

    expect(text('devices-note')).toContain('not every packet on the network')
    expect(text('updated')).toMatch(/^Updated \d/)
    expect(find('devices-capped').exists()).toBe(false)
  })

  it('says when more addresses were seen than are read', async () => {
    const { text } = await open({ answer: devicePage([device()], { capped: true }) })

    expect(text('devices-capped')).toContain('the ones seen most recently')
  })

  describe('the scopes', () => {
    it('have a button each with how many they would show', async () => {
      const { text } = await open()

      expect(text('count-all')).toBe('3')
      expect(text('count-yours')).toBe('1')
      expect(text('count-local')).toBe('0')
      expect(text('count-outside')).toBe('2')
    })

    it('narrow the list, and are kept in the address of the page', async () => {
      const { wrapper, fetchDevices, choose, router } = await open()

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', 'outside')
      })

      expect(last(fetchDevices)).toMatchObject({ scope: 'outside', offset: 0 })
      expect(router.currentRoute.value.query).toEqual({ scope: 'outside' })
    })

    it('go back to every scope', async () => {
      const { wrapper, fetchDevices, choose } = await open({ route: '/devices?scope=yours' })

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', 'all')
      })

      expect(last(fetchDevices).scope).toBeUndefined()
    })

    it('ignore a button with no value', async () => {
      const { wrapper, fetchDevices, choose } = await open()

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', undefined)
      })

      expect(fetchDevices).toHaveBeenCalledTimes(1)
    })

    it('are read from the address of the page', async () => {
      const { fetchDevices, wrapper } = await open({ route: '/devices?scope=local' })

      expect(last(fetchDevices).scope).toBe('local')
      expect(wrapper.findComponent(VBtnToggle).props('modelValue')).toBe('local')
    })
  })

  describe('the other choices', () => {
    it('search by words, named in the address of the page', async () => {
      const { wrapper, fetchDevices } = await open({ route: '/devices?q=tv' })

      expect(last(fetchDevices).q).toBe('tv')
      expect(wrapper.findComponent(AssetSearch).props('modelValue')).toBe('tv')
      expect(wrapper.findComponent(AssetSearch).props('label')).toBe('Search devices')
    })

    it('are searched for with what is typed in the search box', async () => {
      const { wrapper, fetchDevices, choose, router } = await open()

      await choose(() => wrapper.findComponent(AssetSearch).vm.$emit('update:modelValue', 'tv'))

      expect(last(fetchDevices).q).toBe('tv')
      expect(router.currentRoute.value.query).toEqual({ q: 'tv' })
    })

    it('can be narrowed to those connected to or that connected out', async () => {
      const { wrapper, fetchDevices, choose, router } = await open()

      await choose(() => {
        select(wrapper, 'Connections').vm.$emit('update:modelValue', 'incoming')
      })

      expect(last(fetchDevices).direction).toBe('incoming')
      expect(router.currentRoute.value.query).toEqual({ direction: 'incoming' })
      await choose(() => {
        select(wrapper, 'Connections').vm.$emit('update:modelValue', '')
      })
      expect(last(fetchDevices).direction).toBeUndefined()
    })

    it('can be narrowed to those in an incident', async () => {
      const { find, fetchDevices, choose } = await open()

      await choose(() => find('filter-flagged').trigger('click'))

      expect(last(fetchDevices).flagged).toBe(true)
      expect(find('filter-flagged').attributes('aria-pressed')).toBe('true')
    })

    it('can be put in another order', async () => {
      const { wrapper, fetchDevices, choose } = await open()

      await choose(() => {
        select(wrapper, 'Order').vm.$emit('update:modelValue', 'busiest')
      })

      expect(last(fetchDevices).sort).toBe('busiest')
    })

    it('are cleared together, but not the scope or the order', async () => {
      const { find, fetchDevices, choose } = await open({
        route: '/devices?scope=outside&q=tv&flagged=1&sort=address',
      })

      await choose(() => find('clear-filters').trigger('click'))

      expect(last(fetchDevices)).toMatchObject({
        scope: 'outside',
        sort: 'address',
        flagged: false,
      })
      expect(last(fetchDevices).q).toBeUndefined()
      expect(find('clear-filters').exists()).toBe(false)
    })
  })

  describe('when there is nothing to show', () => {
    const none = () => devicePage([])

    it('says that nothing has been reported yet, and leads to the integrations', async () => {
      const { find } = await open({ answer: none() })

      expect(find('devices-empty').text()).toContain('No connections yet')
      expect(find('devices-empty').text()).toContain('last 7 days')
      expect(find('empty-integrations').attributes('href')).toBe('/integrations')
      expect(find('device-list').exists()).toBe(false)
    })

    it('says that nothing matches the choices, and clears them', async () => {
      const { find, fetchDevices, choose } = await open({
        route: '/devices?q=nothing',
        answer: none(),
      })

      expect(find('devices-empty').text()).toContain('Nothing matches')
      await choose(() => find('empty-clear').trigger('click'))
      expect(last(fetchDevices).q).toBeUndefined()
    })

    it('says that nothing is in a scope when the scope is chosen', async () => {
      const { find } = await open({ route: '/devices?scope=local', answer: none() })

      expect(find('devices-empty').text()).toContain('Nothing matches')
    })
  })

  describe('when it cannot load', () => {
    it('says why, and tries again', async () => {
      const { find, fetchDevices, choose } = await open({ answer: offline() })

      expect(find('devices-error').text()).toContain("Can't reach AresGate.")
      fetchDevices.mockResolvedValue(some())

      await choose(() => find('retry').trigger('click'))

      expect(find('devices-error').exists()).toBe(false)
      expect(find('device-list').exists()).toBe(true)
    })

    it('keeps what it has on screen when a later look fails, and says so', async () => {
      const { find, fetchDevices, choose } = await open()
      fetchDevices.mockRejectedValue(offline())

      await choose(() => find('refresh').trigger('click'))

      expect(find('devices-stale').text()).toContain('What is shown is from')
      expect(find('device-list').exists()).toBe(true)
    })
  })

  describe('with the slash key', () => {
    const press = (init: KeyboardEventInit, target: EventTarget = window) => {
      const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
      target.dispatchEvent(event)
      return event
    }

    it('goes to the search from anywhere on the page', async () => {
      const { wrapper } = await open()

      const event = press({ key: '/' })

      expect(event.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(wrapper.find('input').element)
    })

    it('leaves the key alone in a field, so a slash can be typed', async () => {
      const { wrapper } = await open()
      const input = wrapper.find('input').element
      input.blur()

      expect(press({ key: '/' }, input).defaultPrevented).toBe(false)
    })

    it('leaves other keys and shortcuts alone', async () => {
      await open()

      expect(press({ key: 'a' }).defaultPrevented).toBe(false)
      expect(press({ key: '/', ctrlKey: true }).defaultPrevented).toBe(false)
      expect(press({ key: '/', metaKey: true }).defaultPrevented).toBe(false)
      expect(press({ key: '/', altKey: true }).defaultPrevented).toBe(false)
    })

    it('stops listening when the page is left', async () => {
      const { wrapper } = await open()
      wrapper.unmount()

      expect(press({ key: '/' }).defaultPrevented).toBe(false)
    })
  })

  describe('more of them', () => {
    function many(count: number, from = 0) {
      return Array.from({ length: count }, (_, number) =>
        device({ address: `52.1.2.${from + number}` }),
      )
    }

    it('are offered when there are more than were asked for', async () => {
      const { find, text } = await open({ answer: devicePage(many(30), { total: 75 }) })

      expect(text('more')).toContain('Showing 30 of 75.')
      expect(find('show-more').text()).toBe('Show 30 more')
    })

    it('say how many are left when that is fewer than a page', async () => {
      const { find } = await open({ answer: devicePage(many(30), { total: 42 }) })

      expect(find('show-more').text()).toBe('Show 12 more')
    })

    it('are added to the end of the list, from where it stopped', async () => {
      const { find, addresses, fetchDevices, choose } = await open({
        answer: devicePage(many(30), { total: 45 }),
      })
      fetchDevices.mockResolvedValue(devicePage(many(15, 100), { total: 45 }))

      await choose(() => find('show-more').trigger('click'))

      expect(last(fetchDevices)).toMatchObject({ limit: 30, offset: 30 })
      expect(addresses()).toHaveLength(45)
      expect(find('more').exists()).toBe(false)
    })

    it('say why they could not be added, and keep the ones shown', async () => {
      const { find, addresses, fetchDevices, choose } = await open({
        answer: devicePage(many(30), { total: 45 }),
      })
      fetchDevices.mockRejectedValue(offline())

      await choose(() => find('show-more').trigger('click'))

      expect(find('devices-stale').text()).toContain("Can't reach AresGate.")
      expect(addresses()).toHaveLength(30)
    })

    it('are all asked for again when the list is refreshed, so none vanish', async () => {
      const { find, fetchDevices, choose } = await open({
        answer: devicePage(many(30), { total: 45 }),
      })
      fetchDevices.mockResolvedValue(devicePage(many(15, 100), { total: 45 }))
      await choose(() => find('show-more').trigger('click'))
      fetchDevices.mockResolvedValue(devicePage(many(45), { total: 45 }))

      await choose(() => find('refresh').trigger('click'))

      expect(last(fetchDevices)).toMatchObject({ limit: 45, offset: 0 })
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchDevices, choose } = await open()

      await choose(() => find('refresh').trigger('click'))

      expect(fetchDevices).toHaveBeenCalledTimes(2)
    })

    it('asks again every half minute while the page is open, leaving what is on screen alone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchDevices, find } = await open()
        fetchDevices.mockReturnValue(new Promise(() => {}))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchDevices).toHaveBeenCalledTimes(2)
        expect(find('device-list').exists()).toBe(true)
        expect(find('devices-loading').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the answer to a look that a newer one has replaced', async () => {
      const { find, fetchDevices, addresses, choose } = await open()
      let late: (answer: devicesApi.DevicePage) => void = () => {}
      fetchDevices.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchDevices.mockResolvedValueOnce(devicePage([device({ address: '1.1.1.1' })]))

      await choose(() => find('refresh').trigger('click'))
      await choose(() => find('refresh').trigger('click'))
      late(devicePage([device({ address: '9.9.9.9' })]))
      await flushPromises()

      expect(addresses()).toEqual(['1.1.1.1'])
    })

    it('ignores the failure of a look that a newer one has replaced', async () => {
      const { find, fetchDevices, choose } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchDevices.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('refresh').trigger('click'))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('devices-stale').exists()).toBe(false)
    })

    it('ignores the answer for more when a newer look has replaced it', async () => {
      const first = Array.from({ length: 30 }, (_, number) =>
        device({ address: `52.1.2.${number}` }),
      )
      const { find, fetchDevices, addresses, choose } = await open({
        answer: devicePage(first, { total: 45 }),
      })
      let late: (answer: devicesApi.DevicePage) => void = () => {}
      fetchDevices.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchDevices.mockResolvedValueOnce(devicePage([device({ address: '1.1.1.1' })]))

      await choose(() => find('show-more').trigger('click'))
      await choose(() => find('refresh').trigger('click'))
      late(devicePage([device({ address: '9.9.9.9' })], { total: 45 }))
      await flushPromises()

      expect(addresses()).toEqual(['1.1.1.1'])
    })

    it('ignores the failure to get more when a newer look has replaced it', async () => {
      const first = Array.from({ length: 30 }, (_, number) =>
        device({ address: `52.1.2.${number}` }),
      )
      const { find, fetchDevices, choose } = await open({
        answer: devicePage(first, { total: 45 }),
      })
      let fail: (reason: Error) => void = () => {}
      fetchDevices.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      fetchDevices.mockResolvedValueOnce(devicePage([device({ address: '1.1.1.1' })]))
      await choose(() => find('show-more').trigger('click'))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('devices-stale').exists()).toBe(false)
    })
  })
})
