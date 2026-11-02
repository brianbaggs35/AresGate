import AssetSources from '@/components/AssetSources.vue'
import { asset, listed } from '@/test/assets'
import { mountWithPlugins } from '@/test/mount'

describe('AssetSources', () => {
  it('has a chip for each program, with its ways and when it last listed the asset', async () => {
    const { wrapper } = await mountWithPlugins(AssetSources, {
      props: {
        asset: asset({
          listings: [
            listed(),
            listed({ via: 'dhcp', via_label: 'DHCP leases' }),
            listed({
              source: 'wazuh',
              source_name: 'Wazuh',
              via_label: 'Agent',
              matched_by: 'address',
            }),
          ],
        }),
      },
    })

    const chips = wrapper.findAll('li')
    expect(chips).toHaveLength(2)
    expect(wrapper.find('[data-test="asset-source-opnsense"]').text()).toContain(
      'ARP table, DHCP leases',
    )
    expect(wrapper.find('[data-test="asset-source-wazuh"]').text()).toContain(
      'Agent (matched by address)',
    )
    expect(wrapper.find('time').attributes('datetime')).toBe('2026-11-01T11:58:00Z')
  })

  it('says so when no program has listed the asset', async () => {
    const { wrapper } = await mountWithPlugins(AssetSources, {
      props: { asset: asset({ listings: [] }) },
    })

    expect(wrapper.find('[data-test="asset-sources"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="asset-no-sources"]').exists()).toBe(true)
  })
})
