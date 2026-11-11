import AgentSpend from '@/components/AgentSpend.vue'
import { limits, usage } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Partial<InstanceType<typeof AgentSpend>['$props']> = {}) {
  const mounted = await mountWithPlugins(AgentSpend, {
    props: { usage: usage(), limits: limits(), ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('AgentSpend', () => {
  it('says in a line what the agents used of the AI over 30 days', async () => {
    const { find } = await show()

    expect(find('spend-cost').text()).toBe('$0.01')
    expect(find('spend-line').text()).toContain('6 requests')
    expect(find('spend-line').text()).toContain('10.2K tokens')
    expect(find('spend-line').text()).toContain('33% cached')
    expect(find('spend-settings').attributes('href')).toBe('/settings/agents')
  })

  it('says one request in the singular and leaves out the cache before anything was sent', async () => {
    const { find } = await show({ usage: usage({ calls: 1, input_tokens: 0 }) })

    expect(find('spend-line').text()).toContain('1 request ·')
    expect(find('spend-line').text()).not.toContain('cached')
  })

  it('shows nothing until an agent has asked the AI something, and no limit is set', async () => {
    const { find } = await show({ usage: usage({ calls: 0 }) })

    expect(find('agents-spend').exists()).toBe(false)
  })

  it('shows how much of each limit that is set is gone, and none of those that are not', async () => {
    const { find } = await show({
      limits: limits([
        { limit_micros: 1_000_000, spent_micros: 850_000, state: 'warning' },
        { period: 'month', limit_micros: null },
      ]),
    })

    expect(find('spend-limit-day').text()).toContain('Daily limit: $0.85 of $1.00: nearly used up')
    expect(find('spend-limit-day').find('[role="progressbar"]').attributes('aria-valuenow')).toBe(
      '85',
    )
    expect(find('spend-limit-month').exists()).toBe(false)
  })

  it('shows its limits even before anything was spent', async () => {
    const { find } = await show({
      usage: usage({ calls: 0 }),
      limits: limits([{ limit_micros: 1_000_000, spent_micros: 0, state: 'ok' }]),
    })

    expect(find('agents-spend').exists()).toBe(true)
    expect(find('spend-limit-day').text()).toContain('$0.00 of $1.00')
  })
})
