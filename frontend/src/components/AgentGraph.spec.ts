import AgentGraph from '@/components/AgentGraph.vue'
import { EDGES, run, step } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(AgentGraph, {
    props: { edges: EDGES, run: null, steps: [], ...props },
  })
  const states = () =>
    mounted.wrapper.findAll('[data-test="graph-node"]').map((node) => node.attributes('data-state'))
  return { ...mounted, states }
}

describe('AgentGraph', () => {
  it('draws the steps the graph has, in the order they run', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('[data-test="graph-label"]').map((label) => label.text())).toEqual([
      'Plan',
      'Look',
      'Think',
      'Report',
    ])
    expect(wrapper.findAll('.link')).toHaveLength(3)
  })

  it('shows every step waiting when there is no run', async () => {
    const { states } = await open()

    expect(states()).toEqual(['waiting', 'waiting', 'waiting', 'waiting'])
  })

  it('lights the step a run is in, ticks the ones before it and marks it as the current step', async () => {
    const { wrapper, states } = await open({
      run: run({ status: 'running', node: 'act', rounds: 1 }),
      steps: [step({ node: 'plan' }), step({ seq: 2, node: 'act' })],
    })

    expect(states()).toEqual(['done', 'active', 'waiting', 'waiting'])
    const nodes = wrapper.findAll('[data-test="graph-node"]')
    expect(nodes[1]!.attributes('aria-current')).toBe('step')
    expect(nodes[0]!.attributes('aria-current')).toBeUndefined()
    expect(wrapper.findAll('.link--live')).toHaveLength(1)
  })

  it('says in words what each step is doing, and how many steps a step took', async () => {
    const { wrapper } = await open({
      run: run({ status: 'running', node: 'think' }),
      steps: [step({ node: 'act' }), step({ seq: 2, node: 'act' })],
    })

    const says = wrapper.findAll('[data-test="graph-state"]').map((state) => state.text())
    expect(says).toEqual(['Waiting', 'Done · 2 steps', 'Working on it', 'Waiting'])
  })

  it('shows what a run that ended early never reached', async () => {
    const { states } = await open({
      run: run({ status: 'failed' }),
      steps: [step({ node: 'plan' })],
    })

    expect(states()).toEqual(['done', 'skipped', 'skipped', 'skipped'])
  })

  it('counts the rounds of looking again, never past the most there are', async () => {
    const { wrapper } = await open({ run: run({ rounds: 2 }), steps: [step()] })

    expect(wrapper.find('[data-test="graph-loop"]').text()).toContain('up to 3 rounds')
    expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Round 2 of 3')
    expect(wrapper.findAll('.loop__dot--on')).toHaveLength(2)

    await wrapper.setProps({ run: run({ rounds: 9 }) })
    expect(wrapper.findAll('.loop__dot--on')).toHaveLength(3)
  })

  it('has no loop to show for a graph without one', async () => {
    const { wrapper } = await open({
      edges: EDGES.filter((edge) => edge.source !== 'think' || edge.target === 'report'),
    })

    expect(wrapper.find('[data-test="graph-loop"]').exists()).toBe(false)
  })
})
