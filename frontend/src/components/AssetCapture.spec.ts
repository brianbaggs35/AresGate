import * as capturesApi from '@/api/captures'
import { ApiError } from '@/api/client'
import AssetCapture from '@/components/AssetCapture.vue'
import { capture, packet } from '@/test/captures'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(addresses: string[] = ['192.168.1.20'], found = capture()) {
  const take = vi.spyOn(capturesApi, 'takeCapture').mockResolvedValue(found)
  const mounted = await mountWithPlugins(AssetCapture, {
    signedIn: 'admin',
    props: { addresses },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const start = async () => {
    await find('capture-start').trigger('click')
    await flushPromises()
  }
  return { ...mounted, take, find, start }
}

describe('AssetCapture', () => {
  it('listens for ten seconds to the address when asked', async () => {
    const { take, start } = await open()

    await start()

    expect(take).toHaveBeenCalledWith('192.168.1.20', 10, expect.any(String))
  })

  it('shows what was seen: the summary, the protocols and each packet', async () => {
    const { wrapper, find, start } = await open()

    await start()

    expect(find('capture-summary').text()).toBe(
      '3 packets to or from 192.168.1.20 in 10 seconds, 4.0 KB in the capture.',
    )
    expect(wrapper.findAll('[data-test="capture-protocol"]').map((each) => each.text())).toEqual([
      'TCP 3',
    ])
    const rows = wrapper.findAll('[data-test="capture-packet"]')
    expect(rows).toHaveLength(3)
    expect(rows[0]?.text()).toContain('+0.000')
    expect(rows[0]?.text()).toContain('192.168.1.20:50000')
    expect(rows[0]?.text()).toContain('93.184.216.34:80')
    expect(rows[0]?.findAll('td')[3]?.text()).toBe('TCP SYN')
    expect(rows[2]?.text()).toContain('+0.250')
    expect(rows[2]?.text()).toContain('GET / HTTP/1.1..')
    expect(find('capture-notes').exists()).toBe(false)
  })

  it('writes an IPv6 address with its port in brackets and an address with no port bare', async () => {
    const { wrapper, start } = await open(
      ['fe80::1'],
      capture({
        packets: [
          packet({ source: 'fe80::1', destination: 'fe80::2', protocol: 'UDP', flags: '' }),
          packet({ protocol: 'ICMP', source_port: null, destination_port: null, flags: '' }),
        ],
        total: 2,
      }),
    )

    await start()

    const rows = wrapper.findAll('[data-test="capture-packet"]')
    expect(rows[0]?.text()).toContain('[fe80::1]:50000')
    expect(rows[1]?.text()).toContain('192.168.1.20')
    expect(rows[1]?.text()).not.toContain('192.168.1.20:')
  })

  it('says how long to listen for, as chosen', async () => {
    const { wrapper, take, start } = await open()

    await wrapper.findAll('[data-test="capture-seconds"] button')[3]?.trigger('click')
    await start()

    expect(take).toHaveBeenCalledWith('192.168.1.20', 30, expect.any(String))
  })

  it('lets one of several addresses be chosen and starts with the first', async () => {
    const { wrapper, take, start } = await open(['192.168.1.20', 'fe80::1'])

    expect(wrapper.find('[data-test="capture-address"]').exists()).toBe(true)
    await start()

    expect(take).toHaveBeenCalledWith('192.168.1.20', 10, expect.any(String))
  })

  it('listens to the address that was chosen', async () => {
    const { wrapper, take, start } = await open(['192.168.1.20', 'fe80::1'])

    wrapper.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'fe80::1')
    await start()

    expect(take).toHaveBeenCalledWith('fe80::1', 10, expect.any(String))
  })

  it('offers no choice of address when it has one', async () => {
    const { find } = await open()

    expect(find('capture-address').exists()).toBe(false)
  })

  it('cannot be started with no address', async () => {
    const { find } = await open([])

    expect(find('capture-start').attributes('disabled')).toBeDefined()
  })

  it('has no address to listen to when the asset has lost them all', async () => {
    const { wrapper, find } = await open()

    await wrapper.setProps({ addresses: [] })

    expect(find('capture-start').attributes('disabled')).toBeDefined()
  })

  it('says so when nothing was seen', async () => {
    const { find, start } = await open(
      ['192.168.1.20'],
      capture({ packets: [], total: 0, protocols: [], bytes: 24 }),
    )

    await start()

    expect(find('capture-summary').text()).toBe('No packet to or from 192.168.1.20 in 10 seconds.')
    expect(find('capture-packets').exists()).toBe(false)
  })

  it('says what is left out', async () => {
    const { find, start } = await open(
      ['192.168.1.20'],
      capture({ total: 900, skipped: 4, cut: true }),
    )

    await start()

    expect(find('capture-notes').text()).toBe(
      "The first 3 are listed. ntopng sent more than AresGate reads, so the end is missing. 4 frames are neither IP nor ARP and aren't shown.",
    )
  })

  it('says it in the singular for one frame and one packet', async () => {
    const { find, start } = await open(
      ['192.168.1.20'],
      capture({ packets: [packet()], total: 1, skipped: 1 }),
    )

    await start()

    expect(find('capture-summary').text()).toContain('1 packet to or from')
    expect(find('capture-notes').text()).toBe("1 frame is neither IP nor ARP and isn't shown.")
  })

  it('says why when it could not capture, and clears what was shown before', async () => {
    const { find, take, start } = await open()
    await start()
    take.mockRejectedValue(new ApiError(502, 'ntopng said: Not allowed'))

    await start()

    expect(find('capture-failure').text()).toBe('ntopng said: Not allowed')
    expect(find('capture-result').exists()).toBe(false)
  })

  it('starts clear for another asset', async () => {
    const { wrapper, find, start } = await open()
    await start()

    await wrapper.setProps({ addresses: ['192.168.1.30'] })

    expect(find('capture-result').exists()).toBe(false)
    await find('capture-start').trigger('click')
    expect(capturesApi.takeCapture).toHaveBeenLastCalledWith('192.168.1.30', 10, expect.any(String))
  })

  it('keeps the address chosen while the page asks again for the same ones', async () => {
    const { wrapper, find, start } = await open(['192.168.1.20', 'fe80::1'])
    await start()

    await wrapper.setProps({ addresses: ['192.168.1.20', 'fe80::1', '10.0.0.4'] })

    expect(find('capture-result').exists()).toBe(false)
    await find('capture-start').trigger('click')
    expect(capturesApi.takeCapture).toHaveBeenLastCalledWith('192.168.1.20', 10, expect.any(String))
  })
})
