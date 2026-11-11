import AgentUsage from '@/components/AgentUsage.vue'
import { days, usage } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Partial<InstanceType<typeof AgentUsage>['$props']> = {}) {
  const mounted = await mountWithPlugins(AgentUsage, {
    props: { usage: usage(), days: days({ 29: 4_000 }), ...props },
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('AgentUsage', () => {
  it('shows what it cost, how many requests and tokens that was, and how much was cached', async () => {
    const { text } = await show()

    expect(text('usage-cost')).toContain('$0.01')
    expect(text('usage-cost')).toContain('$0.0031 a run')
    expect(text('usage-calls')).toContain('6')
    expect(text('usage-calls')).toContain('In 4 runs')
    expect(text('usage-tokens')).toContain('10.2K')
    expect(text('usage-tokens')).toContain('9,000 sent, 1,200 back')
    expect(text('usage-cached')).toContain('33%')
  })

  it('says so when most of what was sent was cached', async () => {
    const { text } = await show({ usage: usage({ input_tokens: 1_000, cached_tokens: 900 }) })

    expect(text('usage-cached')).toContain('90%')
  })

  it('has nothing to say of the cache before anything is sent', async () => {
    const { text } = await show({
      usage: usage({ calls: 0, runs: 1, input_tokens: 0, output_tokens: 0, cost_micros: 0 }),
      days: days(),
    })

    expect(text('usage-cost')).toContain('No AI used')
    expect(text('usage-cached')).toContain('–')
    expect(text('usage-calls')).toContain('In 1 run')
  })

  it('draws each day, and links to where every request is kept and to the settings', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="usage-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="usage-link"]').attributes('href')).toBe('/ai-usage')
    expect(wrapper.find('[data-test="usage-settings-link"]').attributes('href')).toBe(
      '/settings/agents',
    )
  })

  it('says when a model had no price, so that the cost is at least what is shown', async () => {
    const { text, wrapper } = await show({ usage: usage({ unpriced_calls: 1 }) })

    expect(text('usage-unpriced')).toContain('1 request was to a model whose price')
    expect(text('usage-cost')).toContain('and more')
    expect(text('usage-cost')).toContain('Over its last 30 days')
    await wrapper.setProps({ usage: usage({ unpriced_calls: 2 }) })
    expect(text('usage-unpriced')).toContain('2 requests were to a model')
  })

  it('has no note about prices when every request had one', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="usage-unpriced"]').exists()).toBe(false)
  })
})
