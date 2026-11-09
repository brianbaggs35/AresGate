import AssetEvents from '@/components/AssetEvents.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { event } from '@/test/assetDetail'
import { mountWithPlugins } from '@/test/mount'

describe('AssetEvents', () => {
  it('lists each event with its program, how serious it was, its flow and its signature', async () => {
    const mounted = await mountWithPlugins(AssetEvents, {
      props: {
        events: [
          event(),
          event({
            id: 2,
            source: 'wazuh',
            source_name: 'Wazuh',
            severity: 'high',
            summary: 'sshd: authentication failed',
            signature: 'Brute force',
            src_address: '52.1.2.4',
            src_port: 22,
            dst_address: '192.168.1.20',
            dst_port: null,
            outbound: false,
          }),
        ],
      },
    })
    const items = mounted.wrapper.findAll('[data-test="asset-event"]')

    expect(items).toHaveLength(2)
    expect(items.at(0)?.text()).toContain('Blocked tcp')
    expect(items.at(0)?.text()).toContain('OPNsense')
    expect(items.at(0)?.find('[data-test="asset-event-flow"]').text()).toContain('To 52.1.2.3:443')
    expect(items.at(1)?.text()).toContain('Wazuh')
    expect(items.at(1)?.text()).toContain('Brute force')
    expect(items.at(1)?.findComponent(SeverityChip).props('severity')).toBe('high')
    expect(items.at(1)?.find('[data-test="asset-event-flow"]').text()).toContain('From 52.1.2.4:22')
  })

  it('says where an event went when the address is not known', async () => {
    const mounted = await mountWithPlugins(AssetEvents, {
      props: { events: [event({ dst_address: null, dst_port: null })] },
    })

    expect(mounted.wrapper.find('[data-test="asset-event-flow"]').text()).toContain(
      'To an unknown address',
    )
  })
})
