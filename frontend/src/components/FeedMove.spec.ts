import { VSelect } from 'vuetify/components'

import FeedMove from '@/components/FeedMove.vue'
import { feed, iface } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const INTERFACES = [iface({ id: 1 }), iface({ id: 2, name: 'Guests', role: 'guest' })]

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(FeedMove, {
    props: { feed: feed(), interfaces: INTERFACES, ...props },
  })
  const select = mounted.wrapper.findComponent(VSelect)
  const choose = async (value: number | string) => {
    select.vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  return { ...mounted, select, choose }
}

describe('FeedMove', () => {
  it('names the feed it moves, for a screen reader', async () => {
    const { wrapper } = await open()
    const input = wrapper.find('input[role="combobox"]')
    expect(input.attributes('aria-label')).toBe('Where OPNsense igc0 belongs')
  })

  it('names the list that opens too, which the select would point at a label it does not show', async () => {
    const { select } = await open()

    expect(select.props('listProps')).toEqual({
      'aria-labelledby': undefined,
      'aria-label': 'Places for OPNsense igc0',
    })
  })

  it('offers each interface with its role, then the other places a feed can go', async () => {
    const { select } = await open()

    const titles = (select.props('items') as { title: string }[]).map((item) => item.title)
    expect(titles).toEqual([
      'Internet',
      'Guests',
      'A new interface…',
      'Set aside',
      'Not placed yet',
    ])
    const items = select.props('items') as { props: { subtitle: string } }[]
    expect(items[1]?.props.subtitle).toBe('Guests')
  })

  it('does not offer a new interface where it cannot make one', async () => {
    const { select } = await open({ canCreate: false })

    const titles = (select.props('items') as { title: string }[]).map((item) => item.title)
    expect(titles).not.toContain('A new interface…')
  })

  it('shows where the feed is now', async () => {
    expect((await open()).select.props('modelValue')).toBe('not-placed')
    expect((await open({ feed: feed({ interface_id: 2 }) })).select.props('modelValue')).toBe(2)
    expect((await open({ feed: feed({ ignored: true }) })).select.props('modelValue')).toBe(
      'set-aside',
    )
  })

  it('says where the feed was moved to', async () => {
    const { choose, wrapper } = await open({ feed: feed({ interface_id: 2 }) })

    await choose(1)
    await choose('set-aside')
    await choose('not-placed')
    await choose('new')

    expect(wrapper.emitted('move')).toEqual([
      [{ interface_id: 1 }],
      [{ ignored: true }],
      [{ interface_id: null, ignored: false }],
    ])
    expect(wrapper.emitted('create')).toHaveLength(1)
  })

  it('says nothing when the place it is in is chosen again', async () => {
    const { choose, wrapper } = await open({ feed: feed({ interface_id: 2 }) })

    await choose(2)

    expect(wrapper.emitted('move')).toBeUndefined()
  })

  it('can be switched off while another change is made', async () => {
    const { select } = await open({ disabled: true })
    expect(select.props('disabled')).toBe(true)
  })
})
