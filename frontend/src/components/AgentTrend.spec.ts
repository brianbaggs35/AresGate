import AgentTrend from '@/components/AgentTrend.vue'
import { run } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

describe('AgentTrend', () => {
  it('draws a bar for each run that finished, with a series for each severity', async () => {
    const { wrapper } = await mountWithPlugins(AgentTrend, {
      props: {
        runs: [
          run({ id: 3, by_severity: { high: 1 } }),
          run({ id: 2, status: 'failed', by_severity: { critical: 9 } }),
          run({ id: 1, by_severity: { high: 2, low: 1 } }),
        ],
      },
    })

    expect(wrapper.find('[data-test="agent-trend"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('What it found, run by run')
    expect(wrapper.text()).toContain('Run 1')
    expect(wrapper.text()).toContain('Run 3')
    expect(wrapper.text()).not.toContain('Run 2')
  })

  it('says there is nothing to chart before it has found anything', async () => {
    const { wrapper } = await mountWithPlugins(AgentTrend, { props: { runs: [run()] } })

    expect(wrapper.text()).toContain('Nothing to chart yet')
  })
})
