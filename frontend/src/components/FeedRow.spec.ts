import { VSelect } from 'vuetify/components'

import FeedRow from '@/components/FeedRow.vue'
import { feed, iface } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(FeedRow, {
    props: { feed: feed(), interfaces: [iface()], ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('FeedRow', () => {
  it('names the feed, where it comes from, and when it last reported', async () => {
    const { find } = await open({ feed: feed({ last_seen_at: new Date().toISOString() }) })

    expect(find('feed-name').text()).toBe('OPNsense igc0')
    expect(find('feed-connection').text()).toBe('REST API')
    expect(find('feed-seen').text()).toContain('Last reported')
    expect(find('feed-detail').exists()).toBe(false)
  })

  it('says what else is known of it', async () => {
    const { find } = await open({ feed: feed({ detail: 'live packet capture' }) })
    expect(find('feed-detail').text()).toContain('live packet capture')
  })

  it('hands on where the feed was moved to', async () => {
    const { wrapper } = await open()
    const select = wrapper.findComponent(VSelect)

    select.vm.$emit('update:modelValue', 1)
    select.vm.$emit('update:modelValue', 'new')
    await flushPromises()

    expect(wrapper.emitted('move')).toEqual([[{ interface_id: 1 }]])
    expect(wrapper.emitted('create')).toHaveLength(1)
  })

  it('offers a new interface unless told it cannot', async () => {
    const withIt = await open()
    const without = await open({ canCreate: false })

    const titles = (wrapper: typeof withIt.wrapper) =>
      (wrapper.findComponent(VSelect).props('items') as { title: string }[]).map(
        (item) => item.title,
      )
    expect(titles(withIt.wrapper)).toContain('A new interface…')
    expect(titles(without.wrapper)).not.toContain('A new interface…')
  })
})
