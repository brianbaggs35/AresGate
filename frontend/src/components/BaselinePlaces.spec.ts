import * as api from '@/api/baselines'
import { ApiError } from '@/api/client'
import BaselinePlaces from '@/components/BaselinePlaces.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { place, places } from '@/test/baselines'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(answer: api.BaselinePlaces | Error = places()) {
  const fetchIt = vi.spyOn(api, 'fetchBaselinePlaces')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(BaselinePlaces, {
    signedIn: 'admin',
    props: { address: '192.168.1.20' },
  })
  await flushPromises()
  const find = (name: string) => mounted.wrapper.find(`[data-test="${name}"]`)
  return { ...mounted, fetchIt, find }
}

describe('BaselinePlaces', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(api, 'fetchBaselinePlaces').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(BaselinePlaces, {
      signedIn: 'admin',
      props: { address: '192.168.1.20' },
    })

    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('is titled by the device, and lists its places in words', async () => {
    const { wrapper, fetchIt } = await open()

    expect(fetchIt).toHaveBeenCalledWith('192.168.1.20')
    expect(wrapper.find('[data-test="section-title"]').text()).toBe('laptop')
    const rows = wrapper.findAll('li')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.find('[data-test="place-where"]').text()).toBe('198.51.100.0/24, port 443')
    expect(rows[0]?.find('[data-test="place-expected"]').exists()).toBe(false)
    expect(rows[1]?.find('[data-test="place-where"]').text()).toBe('203.0.113.0/24, no port')
    expect(rows[1]?.find('[data-test="place-expected"]').exists()).toBe(true)
  })

  it('is titled by the address when the device has no name', async () => {
    const { wrapper } = await open(places([place()], { name: null }))

    expect(wrapper.find('[data-test="section-title"]').text()).toBe('192.168.1.20')
  })

  it('says why it could not read, and tries again', async () => {
    const { find, fetchIt } = await open(
      new ApiError(404, 'Nothing is known of where it talks to.', 'not_found'),
    )

    expect(find('places-error').text()).toContain('Nothing is known')
    fetchIt.mockResolvedValue(places())
    await find('places-error').find('button').trigger('click')
    await flushPromises()

    expect(find('places-error').exists()).toBe(false)
    expect(find('places-list').exists()).toBe(true)
  })

  it('reads again for another device, and drops the answer for the one it left', async () => {
    const { wrapper, fetchIt } = await open()
    fetchIt.mockResolvedValue(places([place()], { address: 'fd00::5', name: 'tv' }))

    await wrapper.setProps({ address: 'fd00::5' })
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith('fd00::5')
    expect(wrapper.find('[data-test="section-title"]').text()).toBe('tv')
  })

  it('drops the answer for a device that is no longer shown', async () => {
    const answers = new Map<string, (value: api.BaselinePlaces | Error) => void>()
    vi.spyOn(api, 'fetchBaselinePlaces').mockImplementation(
      (address) =>
        new Promise((resolve, reject) => {
          answers.set(address, (value) => {
            if (value instanceof Error) reject(value)
            else resolve(value)
          })
        }),
    )
    const { wrapper } = await mountWithPlugins(BaselinePlaces, {
      signedIn: 'admin',
      props: { address: '192.168.1.20' },
    })
    await wrapper.setProps({ address: 'fd00::5' })

    answers.get('fd00::5')?.(places([place()], { address: 'fd00::5', name: 'tv' }))
    await flushPromises()
    answers.get('192.168.1.20')?.(places())
    await flushPromises()

    expect(wrapper.find('[data-test="section-title"]').text()).toBe('tv')
  })

  it('drops the failure for a device that is no longer shown', async () => {
    const answers = new Map<string, (value: api.BaselinePlaces | Error) => void>()
    vi.spyOn(api, 'fetchBaselinePlaces').mockImplementation(
      (address) =>
        new Promise((resolve, reject) => {
          answers.set(address, (value) => {
            if (value instanceof Error) reject(value)
            else resolve(value)
          })
        }),
    )
    const { wrapper } = await mountWithPlugins(BaselinePlaces, {
      signedIn: 'admin',
      props: { address: '192.168.1.20' },
    })
    await wrapper.setProps({ address: 'fd00::5' })

    answers.get('192.168.1.20')?.(offline())
    await flushPromises()
    answers.get('fd00::5')?.(places([place()], { address: 'fd00::5', name: 'tv' }))
    await flushPromises()

    expect(wrapper.find('[data-test="places-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="section-title"]').text()).toBe('tv')
  })

  it('calls a place expected, and tells the page', async () => {
    const expectIt = vi.spyOn(api, 'expectPlace').mockResolvedValue(place({ expected: true }))
    const { wrapper } = await open()

    await wrapper.findAll('[data-test="place-expect"]')[0]?.trigger('click')
    await flushPromises()

    expect(expectIt).toHaveBeenCalledWith(
      '192.168.1.20',
      { network: '198.51.100.0/24', port: 443, expected: true },
      expect.any(String),
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('takes the mark off an expected place', async () => {
    const expectIt = vi.spyOn(api, 'expectPlace').mockResolvedValue(place())
    const { wrapper } = await open()

    await wrapper.findAll('[data-test="place-expect"]')[1]?.trigger('click')
    await flushPromises()

    expect(expectIt).toHaveBeenCalledWith(
      '192.168.1.20',
      { network: '203.0.113.0/24', port: 0, expected: false },
      expect.any(String),
    )
  })

  it('expects a place not yet learned, and clears the field', async () => {
    const expectIt = vi.spyOn(api, 'expectPlace').mockResolvedValue(place({ expected: true }))
    const { find } = await open()
    expect(find('place-add').attributes('disabled')).toBeDefined()

    await find('place-network').find('input').setValue(' 192.0.2.0/24 ')
    await find('place-port').find('input').setValue('22')
    await find('place-add').trigger('submit')
    await find('place-add').trigger('click')
    await flushPromises()

    expect(expectIt).toHaveBeenCalledWith(
      '192.168.1.20',
      { network: '192.0.2.0/24', port: 22, expected: true },
      expect.any(String),
    )
    expect((find('place-network').find('input').element as HTMLInputElement).value).toBe('')
  })

  it('says why a place was refused, and keeps what was typed', async () => {
    vi.spyOn(api, 'expectPlace').mockRejectedValue(
      new ApiError(422, 'Places are kept as a /24.', 'unprocessable'),
    )
    const { find } = await open()

    await find('place-network').find('input').setValue('192.0.2.0/16')
    await find('place-add').trigger('click')
    await flushPromises()

    expect(find('places-failure').text()).toBe('Places are kept as a /24.')
    expect((find('place-network').find('input').element as HTMLInputElement).value).toBe(
      '192.0.2.0/16',
    )
  })

  it('asks before it forgets a place, and then does', async () => {
    const forget = vi.spyOn(api, 'forgetPlace').mockResolvedValue(undefined)
    const { wrapper } = await open()

    await wrapper.findAll('[data-test="place-forget"]')[0]?.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('it is new again')
    expect(forget).not.toHaveBeenCalled()
    wrapper.findComponent(ConfirmDialog).vm.$emit('confirm')
    await flushPromises()

    expect(forget).toHaveBeenCalledWith(
      '192.168.1.20',
      { network: '198.51.100.0/24', port: 443 },
      expect.any(String),
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('leaves a place alone when the question is closed', async () => {
    const forget = vi.spyOn(api, 'forgetPlace').mockResolvedValue(undefined)
    const { wrapper } = await open()
    await wrapper.findAll('[data-test="place-forget"]')[0]?.trigger('click')

    wrapper.findComponent(ConfirmDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(false)
    expect(forget).not.toHaveBeenCalled()
  })

  it('says why it could not forget a place', async () => {
    vi.spyOn(api, 'forgetPlace').mockRejectedValue(
      new ApiError(404, 'That place is not known.', 'not_found'),
    )
    const { wrapper, find } = await open()

    await wrapper.findAll('[data-test="place-forget"]')[0]?.trigger('click')
    wrapper.findComponent(ConfirmDialog).vm.$emit('confirm')
    await flushPromises()

    expect(find('places-failure').text()).toBe('That place is not known.')
  })
})
