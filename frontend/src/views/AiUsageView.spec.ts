import type { VueWrapper } from '@vue/test-utils'

import * as usageApi from '@/api/aiUsage'
import { ApiError } from '@/api/client'
import BarChart from '@/charts/BarChart.vue'
import AiCallsTable from '@/components/AiCallsTable.vue'
import AiLevelCard from '@/components/AiLevelCard.vue'
import AiLimitsCard from '@/components/AiLimitsCard.vue'
import { callPage, group, limit, totals, usage } from '@/test/aiUsage'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AiUsageView from '@/views/AiUsageView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(answer: usageApi.Usage | Error = usage()) {
  const fetchIt = vi.spyOn(usageApi, 'fetchUsage')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  vi.spyOn(usageApi, 'fetchUsageCalls').mockResolvedValue(callPage(2))
  const mounted = await mountWithPlugins(AiUsageView, {
    signedIn: 'admin',
    withApp: true,
    route: '/ai-usage',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const chart = (selector: string) =>
    mounted.wrapper
      .findAllComponents(BarChart)
      .find((item) => item.attributes('data-test') === selector) as VueWrapper<
      InstanceType<typeof BarChart>
    >
  return { ...mounted, fetchIt, find, text, chart }
}

describe('AiUsageView', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(usageApi, 'fetchUsage').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AiUsageView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="usage-loading"]').exists()).toBe(true)
  })

  it('is a page of its own, titled as one, with the range and Refresh beside the title', async () => {
    const { find, text } = await open()

    expect(text('page-heading')).toBe('AI usage')
    expect(find('page-description').text()).toContain('The costs are estimates')
    expect(find('range').exists()).toBe(true)
    expect(find('refresh').exists()).toBe(true)
    // The title is the page's, so no card repeats it.
    expect(find('usage-card').find('[data-test="section-title"]').exists()).toBe(false)
  })

  it('keeps the title while it asks, and offers the range only once it has an answer', async () => {
    vi.spyOn(usageApi, 'fetchUsage').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AiUsageView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('AI usage')
    expect(wrapper.find('[data-test="range"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="refresh"]').exists()).toBe(false)
  })

  it('says when the numbers could not be had, and asks again', async () => {
    const { find, fetchIt, text } = await open(offline())
    expect(find('page-heading').text()).toBe('AI usage')
    expect(text('usage-error')).toContain("Can't reach AresGate.")
    fetchIt.mockResolvedValue(usage())

    await find('retry').trigger('click')
    await flushPromises()

    expect(find('usage-error').exists()).toBe(false)
    expect(find('tile-cost').exists()).toBe(true)
  })

  describe('before AI was ever asked', () => {
    it('says so and leads to the setup', async () => {
      const { find, text } = await open(usage({ ever: false }))

      expect(text('usage-never')).toContain("AI hasn't been asked anything yet")
      expect(find('usage-setup').attributes('href')).toBe('/settings/ai')
      expect(find('tile-cost').exists()).toBe(false)
      expect(find('limits-card').exists()).toBe(false)
      expect(find('download').exists()).toBe(false)
    })

    it('still lets the level be chosen, before anything has been asked', async () => {
      const { wrapper } = await open(usage({ ever: false, level: 'low' }))

      expect(wrapper.findComponent(AiLevelCard).props('level')).toBe('low')
    })
  })

  describe('the numbers', () => {
    it('says what the month has cost and where it is heading', async () => {
      const { text } = await open()

      expect(text('tile-month')).toContain('$0.08')
      expect(text('tile-month')).toContain('On course for about $0.16 by the end of the month')
    })

    it('does not guess early in the month', async () => {
      const { text } = await open(usage({ month: { ...usage().month, projected_micros: null } }))

      expect(text('tile-month')).toContain('Too early in the month to say where it is heading')
    })

    it('says what the range cost, and how that compares', async () => {
      const { text } = await open()

      expect(text('tile-cost')).toContain('$0.04')
      expect(text('tile-cost')).toContain('In the last 30 days')
      expect(text('tile-cost')).toContain('more than the 30 days before')
    })

    it('says how many tokens, and how many were cached', async () => {
      const { text } = await open()

      expect(text('tile-tokens')).toContain('27.6K')
      expect(text('tile-tokens')).toContain('25% of what was sent was already cached')
    })

    it('says how many requests, and how many failed', async () => {
      const ok = await open()
      expect(ok.text('tile-requests')).toContain('None failed')
      ok.wrapper.unmount()

      const failed = await open(usage({ totals: totals({ failed: 2 }) }))
      expect(failed.text('tile-requests')).toContain('2 failed')
    })

    it('says the costs are estimates, from where, and when', async () => {
      const { find, text } = await open()

      expect(text('usage-estimate')).toContain('Costs are estimates')
      expect(text('usage-estimate')).toContain('2026-10-27')
      const links = find('usage-estimate').findAll('a')
      expect(links.map((link) => link.text())).toEqual(['Anthropic', 'OpenAI'])
      expect(links[0]?.attributes('href')).toBe(
        'https://platform.claude.com/docs/en/about-claude/pricing',
      )
      expect(links[0]?.attributes('rel')).toBe('noopener noreferrer')
      expect(text('usage-estimate')).not.toContain('no known price')
    })

    it('says which requests have no price', async () => {
      const one = await open(usage({ totals: totals({ unpriced: 1 }) }))
      expect(one.text('usage-estimate')).toContain('1 request used a model with no known price')
      one.wrapper.unmount()

      const some = await open(usage({ totals: totals({ unpriced: 3 }) }))
      expect(some.text('usage-estimate')).toContain('3 requests used a model with no known price')
    })
  })

  describe('the charts', () => {
    it('stacks what each use took each day, in cost to begin with', async () => {
      const { chart } = await open()
      const daily = chart('daily-chart')

      expect(daily.props('title')).toBe('Cost by day')
      expect(daily.props('stacked')).toBe(true)
      expect(daily.props('categories')).toHaveLength(7)
      expect(daily.props('series')).toHaveLength(1)
      expect(daily.props('whole')).toBe(false)
      expect(daily.props('format')?.(0.0415)).toBe('$0.04')
    })

    it('shows tokens or calls instead when asked', async () => {
      const { find, chart } = await open()

      await find('metric-tokens').trigger('click')
      expect(chart('daily-chart').props('title')).toBe('Tokens by day')
      expect(chart('daily-chart').props('whole')).toBe(true)
      expect(chart('groups-chart').props('series')[0]?.values).toEqual([27_600])

      await find('metric-calls').trigger('click')
      expect(chart('daily-chart').props('title')).toBe('Calls by day')
      expect(chart('groups-chart').props('series')[0]?.values).toEqual([12])
    })

    it('ranks the models, and can rank the providers or the uses instead', async () => {
      const { find, chart } = await open()
      expect(chart('groups-chart').props('categories')).toEqual(['Claude Haiku 5.5'])

      await find('grouping-provider').trigger('click')
      expect(chart('groups-chart').props('categories')).toEqual(['Anthropic'])
      expect(chart('groups-chart').props('title')).toBe('Cost by provider')

      await find('grouping-use').trigger('click')
      expect(chart('groups-chart').props('categories')).toEqual(['Reading incidents'])
    })

    it('says which groups have no price', async () => {
      const { text, find } = await open(
        usage({
          by_model: [
            group(),
            group({ key: 'mystery', label: 'mystery', cost_micros: 0, unpriced: 2 }),
          ],
        }),
      )

      expect(text('groups-unpriced')).toBe('mystery: 2 without a price')
      expect(find('groups-unpriced').text()).not.toContain('Claude Haiku')
    })

    it('says nothing about prices when every request has one', async () => {
      const { find } = await open()

      expect(find('groups-unpriced').exists()).toBe(false)
    })
  })

  describe('what took the most', () => {
    it('lists it, linking an incident to its page', async () => {
      const { wrapper } = await open()

      const items = wrapper.findAll('[data-test="top-item"]')
      expect(items).toHaveLength(2)
      expect(items[0]?.text()).toContain('Reading incidents: incident 12')
      expect(items[0]?.text()).toContain('3 requests · 6,900 tokens')
      expect(items[0]?.text()).toContain('$0.01')
      expect(items[0]?.find('[data-test="top-link"]').attributes('href')).toBe('/incidents/12')
      expect(items[1]?.text()).toContain('Summaries: the weekly summary')
      expect(items[1]?.text()).toContain('1 request ·')
      expect(items[1]?.find('[data-test="top-link"]').exists()).toBe(false)
    })

    it('says so when nothing was about anything', async () => {
      const { find } = await open(usage({ top: [] }))

      expect(find('top-empty').exists()).toBe(true)
      expect(find('top-item').exists()).toBe(false)
    })
  })

  describe('choosing the range', () => {
    it('begins with the last 30 days', async () => {
      const { fetchIt } = await open()

      expect(fetchIt).toHaveBeenCalledWith('30d')
    })

    it('asks again for the range chosen, and the list of requests with it', async () => {
      const { find, fetchIt, wrapper } = await open()
      fetchIt.mockResolvedValue(usage({ range: '90d' }))

      await find('range-90d').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenLastCalledWith('90d')
      expect(wrapper.findComponent(AiCallsTable).props('range')).toBe('90d')
      expect(find('tile-cost').text()).toContain('In the last 90 days')
    })

    it('asks again when refreshed', async () => {
      const { find, fetchIt } = await open()

      await find('refresh').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledTimes(2)
    })

    it('keeps what it showed, and says so, when asking again fails', async () => {
      const { find, fetchIt, text } = await open()
      fetchIt.mockRejectedValue(offline())

      await find('refresh').trigger('click')
      await flushPromises()

      expect(text('usage-stale')).toContain("Can't reach AresGate.")
      expect(find('tile-cost').exists()).toBe(true)
    })

    it('drops the answer to a range it is no longer showing', async () => {
      const { find, fetchIt } = await open()
      let answerFirst: (value: usageApi.Usage) => void = () => {}
      fetchIt
        .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
        .mockResolvedValueOnce(usage({ range: '7d' }))

      await find('range-90d').trigger('click')
      await find('range-7d').trigger('click')
      await flushPromises()
      answerFirst(usage({ range: '90d' }))
      await flushPromises()

      expect(find('tile-cost').text()).toContain('In the last 7 days')
    })

    it('drops the failure of a range it is no longer showing', async () => {
      const { find, fetchIt } = await open()
      let failFirst: (error: Error) => void = () => {}
      fetchIt
        .mockReturnValueOnce(new Promise((_, reject) => (failFirst = reject)))
        .mockResolvedValueOnce(usage({ range: '7d' }))

      await find('range-90d').trigger('click')
      await find('range-7d').trigger('click')
      await flushPromises()
      failFirst(offline())
      await flushPromises()

      expect(find('usage-stale').exists()).toBe(false)
    })
  })

  describe('the level', () => {
    it('shows the levels, and takes the new one when it is kept', async () => {
      const { wrapper, find } = await open()
      expect(wrapper.findComponent(AiLevelCard).props('levels')).toHaveLength(5)
      expect(find('level-name').text()).toBe('Medium')

      wrapper.findComponent(AiLevelCard).vm.$emit('changed', 'maximum')
      await flushPromises()

      expect(wrapper.findComponent(AiLevelCard).props('level')).toBe('maximum')
      expect(find('level-name').text()).toBe('Maximum')
    })
  })

  describe('the limits', () => {
    it('shows them, and takes the new ones when they are kept', async () => {
      const { wrapper, find } = await open()
      const kept = [
        limit({ limit_micros: 2_000_000, spent_micros: 12_000, state: 'ok' }),
        limit({ period: 'month' }),
      ]

      wrapper.findComponent(AiLimitsCard).vm.$emit('changed', kept)
      await flushPromises()

      expect(wrapper.findComponent(AiLimitsCard).props('limits')).toEqual(kept)
      expect(find('limit-day-words').text()).toBe('$0.01 of $2.00')
    })
  })

  describe('the spreadsheet', () => {
    it('downloads the range that is shown', async () => {
      const { find } = await open()

      expect(find('download').attributes('href')).toMatch(
        /^\/api\/ai\/usage\.csv\?range=30d&timezone=/,
      )
      expect(find('download').attributes('download')).toBeDefined()
      expect(find('download').text()).toContain('the last 30 days')
    })
  })
})
