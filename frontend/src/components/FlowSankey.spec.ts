import FlowSankey from '@/components/FlowSankey.vue'
import { flow, node } from '@/test/flow'
import { mountWithPlugins } from '@/test/mount'

async function open(props: { flow?: ReturnType<typeof flow>; selected?: string | null } = {}) {
  const mounted = await mountWithPlugins(FlowSankey, {
    withApp: true,
    props: { flow: props.flow ?? flow(), selected: props.selected ?? null },
  })
  const nodes = () => mounted.wrapper.findAll('[role="button"]')
  const find = (id: string) => mounted.wrapper.find(`[data-test="flow-node-${id}"]`)
  const component = () => mounted.wrapper.findComponent(FlowSankey)
  return { ...mounted, nodes, find, component }
}

describe('FlowSankey', () => {
  it('draws a block for each node and a band for each link, each block with a sentence', async () => {
    const { wrapper, nodes } = await open()

    expect(nodes()).toHaveLength(7)
    expect(wrapper.findAll('[data-test="flow-band"]')).toHaveLength(6)
    expect(nodes()[0]!.attributes('aria-label')).toBe('From 192.168.1.20: 7 connections, 1 refused')
    expect(wrapper.find('.flow__svg').attributes('aria-label')).toContain(
      'Traffic from who connected',
    )
    expect(wrapper.text()).toContain('Who connected')
    expect(wrapper.text()).toContain('To which service')
  })

  it('draws the refused part of a band apart from the rest, only where there was some', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('.flow__refused')).toHaveLength(4)
    expect(wrapper.findAll('.flow__allowed')).toHaveLength(6)
  })

  it('says what the colors are, and the legend takes a kind of band off', async () => {
    const { wrapper } = await open()

    expect(wrapper.text()).toContain('Let through')
    expect(wrapper.text()).toContain('Refused')
  })

  it('picks a block with a click, Enter or Space, and puts it down by doing it again', async () => {
    const { find, component } = await open()
    const block = find('source:192.168.1.20')

    await block.trigger('click')
    await block.trigger('keydown', { key: 'Enter' })
    await block.trigger('keydown', { key: ' ' })

    expect(component().emitted('select')).toEqual([
      ['source:192.168.1.20'],
      ['source:192.168.1.20'],
      ['source:192.168.1.20'],
    ])
  })

  it('puts a block down when it is the one that is picked', async () => {
    const { find, component } = await open({ selected: 'source:192.168.1.20' })

    expect(find('source:192.168.1.20').attributes('aria-pressed')).toBe('true')
    expect(find('source:8.8.8.8').attributes('aria-pressed')).toBe('false')
    await find('source:192.168.1.20').trigger('click')

    expect(component().emitted('select')).toEqual([[null]])
  })

  it('dims what is not on a path through the block that is picked or pointed at', async () => {
    const { wrapper, find } = await open({ selected: 'service:tcp/22' })

    expect(find('source:8.8.8.8').classes()).not.toContain('flow__node--dim')
    expect(find('source:192.168.1.20').classes()).toContain('flow__node--dim')
    expect(wrapper.findAll('.flow__band--dim')).toHaveLength(4)

    await find('source:192.168.1.20').trigger('mouseenter')
    expect(find('source:192.168.1.20').classes()).not.toContain('flow__node--dim')
    expect(find('source:8.8.8.8').classes()).toContain('flow__node--dim')

    await wrapper.find('.flow__svg').trigger('mouseleave')
    expect(find('source:8.8.8.8').classes()).not.toContain('flow__node--dim')
  })

  it('lights the paths of the block that has the keyboard, and lets go when it leaves', async () => {
    const { find } = await open()

    await find('service:tcp/22').trigger('focus')
    expect(find('source:192.168.1.20').classes()).toContain('flow__node--dim')

    await find('service:tcp/22').trigger('blur')
    expect(find('source:192.168.1.20').classes()).not.toContain('flow__node--dim')
  })

  it('names the others folded together, in a gray block', async () => {
    const { wrapper } = await open({
      flow: flow({
        nodes: [node({ id: 'source:others', label: 'Others', scope: null, folded: 5, events: 9 })],
        links: [],
      }),
    })

    expect(wrapper.text()).toContain('5 others')
    expect(wrapper.find('.flow__block--others').exists()).toBe(true)
  })

  it('cuts a long name short', async () => {
    const long = 'a'.repeat(80)
    const { wrapper } = await open({
      flow: flow({ nodes: [node({ label: long, events: 5 })], links: [] }),
    })

    const label = wrapper.find('.flow__label').text()
    expect(label).toContain('…')
    expect(label.length).toBeLessThan(60)
  })

  it('says there is nothing to draw when there are no connections', async () => {
    const { wrapper } = await open({ flow: flow({ nodes: [], links: [], events: 0, blocked: 0 }) })

    expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)
    expect(wrapper.find('.flow__svg').exists()).toBe(false)
  })

  it('has the same numbers as a table', async () => {
    const { wrapper } = await open()

    await wrapper.find('[data-test="chart-view"]').trigger('click')

    const rows = wrapper.findAll('tbody tr').map((row) => row.text())
    expect(rows).toHaveLength(6)
    expect(rows[0]).toContain('192.168.1.20')
    expect(rows[0]).toContain('tcp/443 (HTTPS)')
    expect(rows[2]).toContain('100%')
  })

  it('turns off a kind of band with the legend', async () => {
    const { wrapper } = await open()

    const items = () => wrapper.findAll('[data-test="chart-legend-item"]')

    await items()[1]!.trigger('click')
    expect(wrapper.findAll('.flow__refused')).toHaveLength(0)
    expect(wrapper.findAll('.flow__allowed')).toHaveLength(6)

    await items()[1]!.trigger('click')
    await items()[0]!.trigger('click')
    expect(wrapper.findAll('.flow__allowed')).toHaveLength(0)
    expect(wrapper.findAll('.flow__refused')).toHaveLength(4)
  })
})
