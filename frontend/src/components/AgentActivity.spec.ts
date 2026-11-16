import AgentActivity from '@/components/AgentActivity.vue'
import { activity, performance, run } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Partial<InstanceType<typeof AgentActivity>['$props']> = {}) {
  const mounted = await mountWithPlugins(AgentActivity, {
    props: {
      activity: [activity()],
      performance: performance({
        finished: 4,
        succeeded: 3,
        failed: 1,
        average_seconds: 12,
        findings: 5,
      }),
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('AgentActivity', () => {
  it('says how the runs of the last 30 days went', async () => {
    const { find } = await show()

    expect(find('activity-runs').text()).toContain('4')
    expect(find('activity-share').text()).toContain('75%')
    expect(find('activity-time').text()).toContain('12 s')
    expect(find('activity-findings').text()).toContain('5')
  })

  it('shows a dash for what it cannot say before a run has ended', async () => {
    const { find } = await show({ performance: performance() })

    expect(find('activity-share').text()).toContain('–')
    expect(find('activity-time').text()).toContain('–')
  })

  it('lists the latest runs, each leading to its agent, with where it is and when', async () => {
    const { wrapper } = await show({
      activity: [
        activity({
          agent_id: 4,
          agent_name: 'Triage',
          run: run({ id: 9, findings: 2, finished_at: new Date().toISOString() }),
        }),
        activity({
          agent_id: 5,
          agent_name: 'Network',
          run: run({
            id: 8,
            status: 'failed',
            error: 'The AI did not answer.',
            finished_at: new Date().toISOString(),
          }),
        }),
      ],
    })

    const entries = wrapper.findAll('[data-test="activity-entry"]')
    expect(entries.map((entry) => entry.attributes('href'))).toEqual(['/agents/4', '/agents/5'])
    expect(entries[0]!.text()).toContain('Triage')
    expect(entries[0]!.find('[data-test="activity-words"]').text()).toBe('2 findings')
    expect(entries[0]!.find('[data-test="activity-status"]').text()).toBe('Finished')
    expect(entries[0]!.find('[data-test="activity-ago"]').text()).toBe('just now')
    expect(entries[1]!.find('[data-test="activity-words"]').text()).toBe('The AI did not answer.')
    expect(entries[1]!.find('[data-test="activity-status"]').text()).toBe('Failed')
  })

  it('says which step a run that is going has got to', async () => {
    const { find } = await show({
      activity: [
        activity({
          run: run({ status: 'running', node: 'think', finished_at: null }),
        }),
      ],
    })

    expect(find('activity-words').text()).toBe('Think · Asks the AI what it makes of it')
    expect(find('activity-status').text()).toBe('Running')
  })

  it('says a run that is going has no step yet when it has none, and a waiting run is dated by its request', async () => {
    const { wrapper } = await show({
      activity: [
        activity({ run: run({ status: 'running', node: null, finished_at: null }) }),
        activity({
          run: run({ status: 'queued', started_at: null, finished_at: null }),
        }),
      ],
    })

    const words = wrapper.findAll('[data-test="activity-words"]').map((each) => each.text())
    expect(words).toEqual(['Working on it now.', 'Waiting for the worker to start it.'])
  })

  it('shows nothing before an agent has run', async () => {
    const { find } = await show({ activity: [] })

    expect(find('agents-activity').exists()).toBe(false)
  })
})
