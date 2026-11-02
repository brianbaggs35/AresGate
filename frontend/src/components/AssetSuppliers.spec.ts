import AssetSuppliers from '@/components/AssetSuppliers.vue'
import { supplier } from '@/test/assets'
import { mountWithPlugins } from '@/test/mount'

describe('AssetSuppliers', () => {
  it('has a place for each program, saying how it lists devices and how many', async () => {
    const { wrapper } = await mountWithPlugins(AssetSuppliers, {
      props: {
        suppliers: [
          supplier({ assets: 12 }),
          supplier({ key: 'ntopng', name: 'ntopng', ways: ['Active hosts'], assets: 1 }),
        ],
      },
    })

    const first = wrapper.find('[data-test="supplier-opnsense"]')
    expect(first.text()).toContain('Connected')
    expect(first.text()).toContain('lists ARP table and DHCP leases')
    expect(first.find('[data-test="supplier-count"]').text()).toBe('12')
    expect(wrapper.find('[data-test="supplier-ntopng"]').text()).toContain('1 asset')
    expect(wrapper.find('[data-test="supplier-ntopng"]').text()).not.toContain('1 assets')
  })

  it('leads to the page of each program', async () => {
    const { wrapper } = await mountWithPlugins(AssetSuppliers, {
      props: { suppliers: [supplier()] },
    })

    expect(wrapper.find('[data-test="supplier-link-opnsense"]').attributes('href')).toBe(
      '/integrations/opnsense',
    )
  })

  it('says a program is not connected, and gives no count for it when it listed nothing', async () => {
    const { wrapper } = await mountWithPlugins(AssetSuppliers, {
      props: {
        suppliers: [supplier({ key: 'wazuh', name: 'Wazuh', connected: false, assets: 0 })],
      },
    })

    const item = wrapper.find('[data-test="supplier-wazuh"]')
    expect(item.find('[data-test="supplier-state"]').text()).toBe('Not connected')
    expect(item.find('[data-test="supplier-count"]').exists()).toBe(false)
  })

  it('still counts what a program listed before it was disconnected, and says so', async () => {
    const { wrapper } = await mountWithPlugins(AssetSuppliers, {
      props: { suppliers: [supplier({ connected: false, assets: 4 })] },
    })

    const item = wrapper.find('[data-test="supplier-opnsense"]')
    expect(item.find('[data-test="supplier-state"]').text()).toBe('Not connected')
    expect(item.text()).toContain('4 assets listed while it was connected')
  })

  it('does not say that of a program that is connected', async () => {
    const { wrapper } = await mountWithPlugins(AssetSuppliers, {
      props: { suppliers: [supplier({ assets: 4 })] },
    })

    expect(wrapper.text()).toContain('4 assets')
    expect(wrapper.text()).not.toContain('while it was connected')
  })
})
