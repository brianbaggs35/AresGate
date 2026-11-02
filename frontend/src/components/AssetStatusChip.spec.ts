import { ASSET_STATUSES } from '@/api/assets'
import AssetStatusChip from '@/components/AssetStatusChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AssetStatusChip', () => {
  it.each([
    ['online', 'Online'],
    ['recent', 'Seen recently'],
    ['away', 'Not seen for a while'],
  ] as const)('says %s in words', async (status, label) => {
    const { wrapper } = await mountWithPlugins(AssetStatusChip, { props: { status } })

    expect(wrapper.text()).toBe(label)
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('has a word for every state', () => {
    expect(ASSET_STATUSES).toHaveLength(3)
  })
})
