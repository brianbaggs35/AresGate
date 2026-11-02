import AssetCard from '@/components/AssetCard.vue'
import AssetSources from '@/components/AssetSources.vue'
import AssetStatusChip from '@/components/AssetStatusChip.vue'
import { asset, listed, machine } from '@/test/assets'
import { mountWithPlugins } from '@/test/mount'

async function open(item = asset(), interfaces: string[] = []) {
  const mounted = await mountWithPlugins(AssetCard, { props: { asset: item, interfaces } })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  const has = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).exists()
  return { ...mounted, text, has }
}

describe('AssetCard', () => {
  it('has the name as a heading, with who made it and its hardware address', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.find('h3').text()).toBe('Laptop')
    expect(text('asset-identity')).toBe('Example Devices Inc. · 00:11:22:0a:0b:0c')
  })

  it('does not say the name twice when the name is the maker or the hardware address', async () => {
    const byMaker = await open(asset({ name: 'Example Devices Inc.' }))
    expect(byMaker.text('asset-identity')).toBe('00:11:22:0a:0b:0c')

    const byAddress = await open(asset({ name: '00:11:22:0a:0b:0c' }))
    expect(byAddress.text('asset-identity')).toBe('Example Devices Inc.')

    const nothingElse = await open(asset({ name: '00:11:22:0a:0b:0c', vendor: null }))
    expect(nothingElse.has('asset-identity')).toBe(false)
  })

  it('says whether it is on the network, and when it was listed', async () => {
    const { wrapper, text } = await open(asset({ status: 'away' }))

    expect(wrapper.findComponent(AssetStatusChip).props('status')).toBe('away')
    expect(wrapper.classes()).toContain('asset--away')
    expect(text('asset-when')).toContain('Listed')
    expect(wrapper.find('time').attributes('datetime')).toBe('2026-11-01T11:58:00Z')
  })

  it('has its addresses, and says how many more there are', async () => {
    const some = await open(asset({ addresses: ['10.0.0.1', '10.0.0.2'], current_addresses: 2 }))
    expect(
      some.wrapper.findAll('[data-test="asset-addresses"] span').map((address) => address.text()),
    ).toEqual(['10.0.0.1', '10.0.0.2'])
    expect(some.has('asset-more')).toBe(false)

    const many = await open(
      asset({
        addresses: ['10.0.0.1', '10.0.0.2', '10.0.0.3', '10.0.0.4', '10.0.0.5'],
        current_addresses: 5,
      }),
    )
    expect(many.text('asset-more')).toBe('+2 more')

    const none = await open(asset({ addresses: [], current_addresses: 0 }))
    expect(none.text('asset-addresses')).toBe('None listed')
  })

  it('has the programs that list it', async () => {
    const { wrapper } = await open()

    expect(wrapper.findComponent(AssetSources).props('asset').listings).toHaveLength(1)
  })

  it('names the interfaces it is on, if any', async () => {
    const none = await open()
    expect(none.has('asset-interfaces')).toBe(false)

    const some = await open(asset(), ['Home', 'IoT'])
    expect(some.text('asset-interfaces')).toBe('Home, IoT')
  })

  describe('flags', () => {
    it('has none for an ordinary device', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('.asset__flags').exists()).toBe(false)
    })

    it('says it is new, uses a private hardware address and says nothing of what it is', async () => {
      const { has, text } = await open(
        asset({ is_new: true, private_mac: true, identified: false }),
      )

      expect(text('asset-new')).toBe('New this week')
      expect(text('asset-private')).toBe('Private hardware address')
      expect(text('asset-unidentified')).toBe('Nothing says what it is')
      expect(has('asset-new')).toBe(true)
    })
  })

  describe('a machine no device matched', () => {
    it('says which program lists it and how it is doing, not a hardware address', async () => {
      const { text } = await open(machine())

      expect(text('asset-identity')).toBe('Wazuh agent · active')
    })

    it('says only the program when it gives no word on how it is doing', async () => {
      const { text } = await open(
        machine({
          listings: [
            listed({ source: 'wazuh', source_name: 'Wazuh', via_label: 'Agent', state: null }),
          ],
        }),
      )

      expect(text('asset-identity')).toBe('Wazuh agent')
    })
  })
})
