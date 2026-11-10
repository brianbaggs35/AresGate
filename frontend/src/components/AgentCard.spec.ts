import AgentCard from '@/components/AgentCard.vue'
import { agent, run } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(item = agent(), busy = false) {
  const mounted = await mountWithPlugins(AgentCard, { props: { agent: item, busy } })
  return {
    ...mounted,
    find: (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`),
  }
}

describe('AgentCard', () => {
  it('names the agent and its kind and schedule, and opens its page', async () => {
    const { find } = await open()

    expect(find('agent-open').text()).toBe('Night watch')
    expect(find('agent-open').attributes('href')).toBe('/agents/3')
    expect(find('agent-kind').text()).toBe('Threat hunter · Every hour')
  })

  it('says whether it is going, in words', async () => {
    const { find } = await open(agent({ state: 'running' }))

    expect(find('agent-state').text()).toBe('Running now')
  })

  it('draws how its last runs went, and says it in words for a screen reader', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.findAll('[data-test="agent-dot"]')).toHaveLength(3)
    expect(find('agent-recent-text').text()).toBe('Its last 3 runs: 2 finished, 1 failed.')
  })

  it('says it has not run when it has not', async () => {
    const { find } = await open(agent({ recent: [], last_run: null }))

    expect(find('agent-recent-text').text()).toBe('It has not run yet.')
    expect(find('agent-recent').text()).toContain('No runs yet')
    expect(find('agent-outcome').text()).toContain('Start it to see what it finds.')
  })

  it('says what its last run came to, and when', async () => {
    const { find } = await open(
      agent({ last_run: run({ findings: 2, finished_at: new Date().toISOString() }) }),
    )

    expect(find('agent-outcome').text()).toBe('2 findings · Ran just now')
  })

  it('says when it runs next when it has not run', async () => {
    const { find } = await open(
      agent({
        last_run: null,
        recent: [],
        next_run_at: new Date(Date.now() + 2 * 3_600_000 + 60_000).toISOString(),
      }),
    )

    expect(find('agent-outcome').text()).toContain('Runs in 2 hours')
  })

  it('says nothing of when for one that is going or has no schedule', async () => {
    const going = await open(
      agent({ state: 'running', last_run: run({ status: 'running', finished_at: null }) }),
    )
    const manual = await open(
      agent({ last_run: null, recent: [], interval_minutes: null, next_run_at: null }),
    )

    expect(going.find('agent-outcome').text()).toBe('Working on it now.')
    expect(manual.find('agent-outcome').text()).toBe('Start it to see what it finds.')
    expect(manual.find('agent-kind').text()).toBe('Threat hunter · Only when you start it')
  })

  it('says it is paused, and does not say when it runs', async () => {
    const { find } = await open(
      agent({ enabled: false, state: 'paused', last_run: null, recent: [] }),
    )

    expect(find('agent-kind').text()).toBe('Threat hunter · Paused')
    expect(find('agent-outcome').text()).not.toContain('Runs')
  })

  it('asks for a run with the button', async () => {
    const { wrapper, find } = await open()

    await find('agent-run').trigger('click')

    expect(wrapper.emitted('run')).toHaveLength(1)
  })

  it('cannot be run while it is going or waiting', async () => {
    const going = await open(agent({ state: 'running' }))
    const waiting = await open(agent({ state: 'queued' }))

    expect(going.find('agent-run').attributes('disabled')).toBeDefined()
    expect(waiting.find('agent-run').attributes('disabled')).toBeDefined()
  })

  it('cannot be run while it is busy being asked', async () => {
    const { find } = await open(agent(), true)

    expect(find('agent-run').attributes('disabled')).toBeDefined()
  })

  it('says one that tests the network has to be allowed first, and cannot be run until it is', async () => {
    const blocked = await open(agent({ active: true, allow_active: false, interval_minutes: null }))
    const allowed = await open(agent({ active: true, allow_active: true, interval_minutes: null }))

    expect(blocked.find('agent-run').attributes('disabled')).toBeDefined()
    expect(blocked.find('agent-blocked').text()).toBe('Allow it to test the network first.')
    expect(allowed.find('agent-run').attributes('disabled')).toBeUndefined()
    expect(allowed.find('agent-blocked').exists()).toBe(false)
  })
})
