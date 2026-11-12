import AssetKindChip from '@/components/AssetKindChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AssetKindChip', () => {
  it('says the kind in words', async () => {
    const { wrapper } = await mountWithPlugins(AssetKindChip, {
      props: { kind: 'camera', label: 'Camera or doorbell' },
    })

    expect(wrapper.find('[data-test="asset-kind"]').text()).toBe('Camera or doorbell')
    expect(wrapper.find('.v-chip--size-small').exists()).toBe(true)
  })

  it('can be the usual size', async () => {
    const { wrapper } = await mountWithPlugins(AssetKindChip, {
      props: { kind: 'router', label: 'Router', size: 'default' },
    })

    expect(wrapper.find('.v-chip--size-default').exists()).toBe(true)
  })
})
