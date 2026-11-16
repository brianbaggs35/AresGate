import * as api from '@/api/baselines'
import { ApiError } from '@/api/client'
import BaselineInterface from '@/components/BaselineInterface.vue'
import BaselinePlaces from '@/components/BaselinePlaces.vue'
import { interfaces, places, talker, talkers } from '@/test/baselines'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import BaselinesView from '@/views/BaselinesView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open({
  route = '/baselines',
  learned = interfaces(),
  devices = talkers(),
}: {
  route?: string
  learned?: api.BaselineInterfaces | Error
  devices?: api.BaselineTalkers | Error
} = {}) {
  const fetchInterfaces = vi.spyOn(api, 'fetchBaselineInterfaces')
  if (learned instanceof Error) fetchInterfaces.mockRejectedValue(learned)
  else fetchInterfaces.mockResolvedValue(learned)
  const fetchTalkers = vi.spyOn(api, 'fetchBaselineTalkers')
  if (devices instanceof Error) fetchTalkers.mockRejectedValue(devices)
  else fetchTalkers.mockResolvedValue(devices)
  vi.spyOn(api, 'fetchBaselinePlaces').mockResolvedValue(places())
  const mounted = await mountWithPlugins(BaselinesView, {
    signedIn: 'admin',
    withApp: true,
    route,
  })
  await flushPromises()
  const find = (name: string) => mounted.wrapper.find(`[data-test="${name}"]`)
  return { ...mounted, fetchInterfaces, fetchTalkers, find }
}

describe('BaselinesView', () => {
  it('has a heading, and a skeleton until the answers arrive', async () => {
    vi.spyOn(api, 'fetchBaselineInterfaces').mockReturnValue(new Promise(() => {}))
    vi.spyOn(api, 'fetchBaselineTalkers').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(BaselinesView, {
      signedIn: 'admin',
      withApp: true,
      route: '/baselines',
    })

    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('Baselines')
    expect(wrapper.findAll('.v-skeleton-loader')).toHaveLength(2)
  })

  it('draws what is usual for each interface and direction', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAllComponents(BaselineInterface)).toHaveLength(2)
  })

  it('says that no counters are collected, and what to do about it', async () => {
    const { find } = await open({ learned: interfaces({ series: [], counted: false }) })

    expect(find('interfaces-uncounted').text()).toContain('Connect your firewall')
  })

  it('says how long learning takes when counters are collected but nothing is learned', async () => {
    const { find } = await open({ learned: interfaces({ series: [] }) })

    expect(find('interfaces-learning').text()).toBe(
      'Still learning. It takes about 4 weeks of counters, and at least 8 readings of an hour of the day, before it says what is usual for that hour.',
    )
  })

  it('lists the devices with how many places they have and whether they are judged', async () => {
    const { wrapper } = await open({
      devices: talkers([
        talker(),
        talker({ address: '192.168.1.30', name: null, places: 2, expected: 0, judged: false }),
      ]),
    })

    const rows = wrapper.findAll('[data-test="talker"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.find('[data-test="talker-name"]').text()).toBe('laptop')
    expect(rows[0]?.text().replace(/\s+/g, ' ')).toContain('Places: 25 (1 expected)')
    expect(rows[0]?.find('[data-test="talker-state"]').text()).toBe('Judged')
    expect(rows[1]?.find('[data-test="talker-name"]').text()).toBe('192.168.1.30')
    expect(rows[1]?.text()).not.toContain('expected')
    expect(rows[1]?.find('[data-test="talker-state"]').text()).toBe('Learning')
    expect(wrapper.find('[data-test="talkers-rule"]').text()).toContain('7 days')
  })

  it('says when there is nothing learned of where devices talk to', async () => {
    const { find } = await open({ devices: talkers([]) })

    expect(find('talkers-empty').text()).toContain('Nothing is learned yet')
  })

  it('says when more devices have places than are listed', async () => {
    const { wrapper } = await open({ devices: { ...talkers(), total: 300 } })

    expect(wrapper.text().replace(/\s+/g, ' ')).toContain(
      'Only the devices with the most places are listed: 1 of 300.',
    )
  })

  it('opens the places of a device, and puts it in the address', async () => {
    const { wrapper, router, find } = await open()
    expect(find('baseline-places').exists()).toBe(false)

    await wrapper.find('[data-test="talker"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ device: '192.168.1.20' })
    expect(wrapper.findComponent(BaselinePlaces).props('address')).toBe('192.168.1.20')
  })

  it('closes it with a second press', async () => {
    const { wrapper, router } = await open({ route: '/baselines?device=192.168.1.20' })
    expect(wrapper.findComponent(BaselinePlaces).exists()).toBe(true)

    await wrapper.find('[data-test="talker"]').trigger('click')
    await flushPromises()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({})
    })

    expect(wrapper.findComponent(BaselinePlaces).exists()).toBe(false)
  })

  it('reads the devices again when a place was changed', async () => {
    const { wrapper, fetchTalkers } = await open({ route: '/baselines?device=192.168.1.20' })

    wrapper.findComponent(BaselinePlaces).vm.$emit('changed')
    await flushPromises()

    expect(fetchTalkers).toHaveBeenCalledTimes(2)
  })

  it('says why it could not read, and tries again, each part by itself', async () => {
    const { find, fetchInterfaces, fetchTalkers } = await open({
      learned: offline(),
      devices: offline(),
    })

    expect(find('interfaces-error').exists()).toBe(true)
    expect(find('talkers-error').exists()).toBe(true)
    fetchInterfaces.mockResolvedValue(interfaces())
    await find('interfaces-error').find('button').trigger('click')
    await flushPromises()
    fetchTalkers.mockResolvedValue(talkers())
    await find('talkers-error').find('button').trigger('click')
    await flushPromises()

    expect(find('interfaces-error').exists()).toBe(false)
    expect(find('talkers-error').exists()).toBe(false)
    expect(find('talkers-list').exists()).toBe(true)
  })

  it('keeps what it has when a later ask fails, and reads everything again on refresh', async () => {
    const { find, fetchInterfaces, fetchTalkers } = await open()
    fetchInterfaces.mockRejectedValue(offline())
    fetchTalkers.mockRejectedValue(offline())

    await find('refresh').trigger('click')
    await flushPromises()

    expect(find('interfaces-list').exists()).toBe(true)
    expect(find('talkers-list').exists()).toBe(true)
    expect(fetchInterfaces).toHaveBeenCalledTimes(2)
  })
})
