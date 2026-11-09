import AssetPeers from '@/components/AssetPeers.vue'
import { peer } from '@/test/assetDetail'
import { mountWithPlugins } from '@/test/mount'

describe('AssetPeers', () => {
  it('lists what it talked to, and what talked to it, with how often and when', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [peer(), peer({ address: '52.1.2.4', events: 1 })],
        contactedBy: [peer({ address: '192.168.1.30', events: 2 })],
      },
    })
    const talks = mounted.wrapper.findAll('[data-test="asset-talks-to"] [data-test="asset-peer"]')
    const contacts = mounted.wrapper.findAll(
      '[data-test="asset-contacted-by"] [data-test="asset-peer"]',
    )

    expect(talks.map((item) => item.text())).toEqual([
      expect.stringContaining('52.1.2.3'),
      expect.stringContaining('52.1.2.4'),
    ])
    expect(talks.at(0)?.text()).toContain('3 events')
    expect(talks.at(1)?.text()).toContain('1 event,')
    expect(contacts).toHaveLength(1)
    expect(contacts.at(0)?.text()).toContain('192.168.1.30')
    expect(contacts.at(0)?.text()).toContain('2 events')
  })

  it('says when nothing has been talked to, or talked to it, in the week', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: { talksTo: [], contactedBy: [] },
    })

    expect(mounted.wrapper.find('[data-test="asset-talks-to-none"]').exists()).toBe(true)
    expect(mounted.wrapper.find('[data-test="asset-contacted-by-none"]').exists()).toBe(true)
    expect(mounted.wrapper.find('[data-test="asset-talks-to"]').exists()).toBe(false)
  })
})
