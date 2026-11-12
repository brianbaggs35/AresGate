import AssetCard from '@/components/AssetCard.vue'
import IncidentThrough from '@/components/IncidentThrough.vue'
import { asset, profile } from '@/test/assets'
import { through } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(...stops: ReturnType<typeof through>[]) {
  const { wrapper } = await mountWithPlugins(IncidentThrough, { props: { through: stops } })
  return wrapper
}

describe('IncidentThrough', () => {
  it('lists the devices in order, each as the Assets page lists it', async () => {
    const wrapper = await show(
      through({ role: 'gateway', address: '192.168.1.1', asset: asset({ key: 'device-1' }) }),
      through({ role: 'target', address: '192.168.1.20', asset: asset({ key: 'device-2' }) }),
    )

    expect(
      wrapper.findAll('[data-test="through-stop"]').map((each) => each.attributes('data-role')),
    ).toEqual(['gateway', 'target'])
    expect(wrapper.findAllComponents(AssetCard).map((each) => each.props('asset').key)).toEqual([
      'device-1',
      'device-2',
    ])
  })

  it('says why each is there and how many alerts name it', async () => {
    const wrapper = await show(
      through({ role: 'gateway', signals: 1 }),
      through({ role: 'target', signals: 3 }),
      through({ role: 'also', signals: 2 }),
    )

    expect(wrapper.findAll('[data-test="through-role"]').map((each) => each.text())).toEqual([
      'Crossed on the way',
      'The device it was about',
      'Also in it',
    ])
    expect(wrapper.findAll('[data-test="through-signals"]').map((each) => each.text())).toEqual([
      '1 alert names it',
      '3 alerts name it',
      '2 alerts name it',
    ])
  })

  it('asks the owner to say what a device is when they have not', async () => {
    const wrapper = await show(through({ asset: asset({ key: 'device-7', profile: null }) }))

    const ask = wrapper.find('[data-test="through-classify"]')
    expect(ask.text()).toBe('Say what it is')
    expect(ask.attributes('href')).toBe('/assets/device-7')
  })

  it('does not ask when the owner has said', async () => {
    const wrapper = await show(through({ asset: asset({ profile: profile() }) }))

    expect(wrapper.find('[data-test="through-classify"]').exists()).toBe(false)
  })

  it('says so for an address that no asset has, rather than hiding it', async () => {
    const wrapper = await show(through({ address: '192.168.1.77', asset: null }))

    expect(wrapper.find('[data-test="through-address"]').text()).toBe('192.168.1.77')
    expect(wrapper.find('[data-test="through-bare"]').text()).toContain('Not on the Assets list')
    expect(wrapper.findComponent(AssetCard).exists()).toBe(false)
  })
})
