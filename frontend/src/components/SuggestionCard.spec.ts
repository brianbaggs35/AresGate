import SuggestionCard from '@/components/SuggestionCard.vue'
import { feed, suggestion } from '@/test/interfaces'
import { mountWithPlugins } from '@/test/mount'

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(SuggestionCard, {
    props: {
      suggestion: suggestion(),
      feeds: [feed({ id: 2, native_name: 'igc2' }), feed({ id: 3, integration_name: 'ntopng' })],
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('SuggestionCard', () => {
  it('says what it would make, why, and which feeds are in it', async () => {
    const { wrapper, find } = await open()

    expect(find('suggestion-name').text()).toBe('Guests')
    expect(wrapper.text()).toContain('Guests')
    expect(find('suggestion-reason').text()).toBe('OPNsense igc2 and ntopng eth2 share a name.')
    expect(wrapper.findAll('[data-test="suggestion-feed"]').map((each) => each.text())).toEqual([
      'OPNsense igc2',
      'ntopng igc0',
    ])
  })

  it('says when the interface is yet to be made', async () => {
    expect((await open()).wrapper.text()).toContain('New')
    expect(
      (await open({ suggestion: suggestion({ interface_id: 4 }) })).wrapper.text(),
    ).not.toContain('New')
  })

  it('does nothing until one of its buttons is pressed', async () => {
    const { wrapper, find } = await open()
    expect(wrapper.emitted()).not.toHaveProperty('confirm')

    await find('suggestion-confirm').trigger('click')
    await find('suggestion-change').trigger('click')
    await find('suggestion-ignore').trigger('click')

    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('change')).toHaveLength(1)
    expect(wrapper.emitted('ignore')).toHaveLength(1)
  })

  it('cannot be answered while another change is under way', async () => {
    const { find } = await open({ busy: true })

    for (const name of ['confirm', 'change', 'ignore']) {
      expect(find(`suggestion-${name}`).attributes('disabled')).toBeDefined()
    }
  })

  it('cannot be changed when it joins an interface that is already there', async () => {
    const { find } = await open({ suggestion: suggestion({ interface_id: 4 }) })
    expect(find('suggestion-change').exists()).toBe(false)
  })
})
