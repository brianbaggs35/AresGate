import IncidentPath from '@/components/IncidentPath.vue'
import { hop, travelPath } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(changes: Parameters<typeof travelPath>[0] = {}) {
  const { wrapper } = await mountWithPlugins(IncidentPath, { props: { path: travelPath(changes) } })
  return wrapper
}

describe('IncidentPath', () => {
  it('draws the stops in order from the internet to the device', async () => {
    const wrapper = await show()

    expect(
      wrapper.findAll('[data-test="path-hop"]').map((each) => each.attributes('data-kind')),
    ).toEqual(['internet', 'firewall', 'agent', 'device'])
    expect(wrapper.findAll('[data-test="hop-subject"]').map((each) => each.text())).toEqual([
      '93.184.216.34',
      'OPNsense',
      'Wazuh',
      'workstation',
    ])
  })

  it('says which way it went and which programs saw it on the way', async () => {
    const wrapper = await show()

    expect(wrapper.find('[data-test="path-lead"]').text()).toBe(
      'It came in from the internet and OPNsense and Wazuh saw it on the way.',
    )
  })

  it('says what a program saw and what it did about it', async () => {
    const wrapper = await show()

    expect(wrapper.findAll('[data-test="hop-seen"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-test="hop-seen"]')[0]?.text()).toMatch(/^12 alerts, from /)
    expect(wrapper.findAll('[data-test="hop-seen"]')[1]?.text()).toMatch(/^1 alert, from /)
    expect(wrapper.find('[data-test="hop-note"]').text()).toBe('Turned it away 12 times.')
  })

  it('says what the address is called where that is known', async () => {
    const wrapper = await show()

    expect(wrapper.find('[data-test="hop-name"]').text()).toBe('scanner-17.example.net')
  })

  it('says a program saw it without a time where it gave none', async () => {
    const wrapper = await show({
      hops: [
        hop(),
        hop({ kind: 'monitor', subject: 'ntopng', source: 'ntopng', alerts: 3 }),
        hop({ kind: 'device', subject: 'workstation' }),
      ],
    })

    expect(wrapper.find('[data-test="hop-seen"]').text()).toBe('3 alerts')
    expect(wrapper.find('[data-test="hop-name"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="hop-note"]').exists()).toBe(false)
  })

  it('says it went out from the device where it did', async () => {
    const wrapper = await show({
      direction: 'outbound',
      hops: [hop({ kind: 'device', subject: 'workstation' }), hop()],
    })

    expect(wrapper.find('[data-test="path-lead"]').text()).toBe(
      'It went out from the device to the internet.',
    )
  })
})
