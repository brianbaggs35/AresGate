import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import NoiseCard from '@/components/NoiseCard.vue'
import { noisySignature, sourceAlerts } from '@/test/dashboard'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'

const noise = {
  sources: [
    sourceAlerts({ total: 120, serious: 100 }),
    sourceAlerts({ source: 'wazuh', source_name: 'Wazuh', total: 30, serious: 0 }),
  ],
  signatures: [
    noisySignature(),
    noisySignature({
      source: 'wazuh',
      source_name: 'Wazuh',
      signature: null,
      severity: 'low',
      count: 1,
      from_addresses: 1,
      to_addresses: 1,
    }),
    noisySignature({
      signature: 'Insecure protocol',
      severity: 'medium',
      count: 30,
      verdict: 'low_priority',
      verdict_rule_id: 4,
    }),
  ],
}

async function open(props: Partial<InstanceType<typeof NoiseCard>['$props']> = {}) {
  const mounted = await mountWithPlugins(NoiseCard, {
    signedIn: 'admin',
    withApp: true,
    props: { noise, total: 150, window: '24h', lastWords: 'the last 24 hours', ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, text: (selector: string) => find(selector).text() }
}

describe('NoiseCard', () => {
  it('says what it is for and where the alerts come from', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.find('h2').text()).toBe('What is making the noise')
    expect(text('section-description')).toBe(
      'The alerts that were reported most in the last 24 hours.',
    )
    expect(text('noise-summary')).toBe(
      'ntopng reported 120 of the 150 alerts (80%), 100 of them high or critical.',
    )
    expect(wrapper.findAll('[data-test="noise-source"]').map((item) => item.text())).toEqual([
      'ntopng: 120, 100 serious',
      'Wazuh: 30',
    ])
  })

  it('lists each alert with how many there were, how big a part that is and who sent it', async () => {
    const { wrapper } = await open()
    const [first, second] = wrapper.findAll('[data-test="noise-item"]')

    expect(first?.find('[data-test="noise-name"]').text()).toBe('Blacklisted flow')
    expect(first?.find('[data-test="noise-count"]').text()).toBe('120 · 80%')
    expect(first?.find('[data-test="noise-program"]').text()).toBe('ntopng')
    expect(first?.find('[data-test="noise-reach"]').text()).toBe('From 3 addresses to 9')
    expect(first?.find('[data-test="severity"]').text()).toBe('High')
    expect(first?.find('.noise__bar > span').attributes('style')).toContain('width: 80%')
    // An alert that names no rule says so, and is not given a verdict by its name.
    expect(second?.find('[data-test="noise-name"]').text()).toBe('Alerts that name no rule')
    expect(second?.find('[data-test="noise-reach"]').text()).toBe('From 1 address to 1')
    expect(second?.find('[data-test="noise-quiet"]').exists()).toBe(false)
    expect(second?.find('.noise__bar > span').attributes('style')).toContain('width: 2%')
  })

  it('shows what the owner already said instead of offering to quiet it', async () => {
    const { wrapper } = await open()
    const third = wrapper.findAll('[data-test="noise-item"]')[2]

    expect(third?.find('[data-test="verdict"]').text()).toBe('Low priority')
    expect(third?.find('[data-test="noise-quiet"]').exists()).toBe(false)
  })

  it('leads to the logs of each alert, for the window of the dashboard', async () => {
    const { wrapper } = await open({ window: '7d' })
    const link = wrapper.find('[data-test="noise-logs"]')

    const href = new URL(link.attributes('href') as string, 'https://aresgate.test')
    expect(href.pathname).toBe('/logs')
    expect(href.searchParams.get('q')).toBe(
      'kind:alert source:ntopng signature:"Blacklisted flow" since:7d',
    )
    expect(link.attributes('aria-label')).toBe('See in logs: Blacklisted flow')
  })

  describe('quieting an alert', () => {
    async function press() {
      const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(given())
      const mounted = await open()
      await mounted.find('noise-quiet').trigger('click')
      await flushPromises()
      return { ...mounted, give }
    }

    it('gives a low priority verdict for the alert from that program, with a note', async () => {
      const { give, wrapper } = await press()

      expect(give).toHaveBeenCalledWith(
        {
          verdict: 'low_priority',
          source: 'ntopng',
          signature: 'Blacklisted flow',
          note: 'Quieted from the dashboard: reported 120 times in the last 24 hours.',
        },
        expect.any(String),
      )
      const [[said]] = wrapper.findComponent(NoiseCard).emitted('judged') as [
        [{ kind: string; rule: unknown }],
      ]
      expect(said.kind).toBe('low_priority')
      expect(said.rule).toEqual(given())
    })

    it('says so when it could not', async () => {
      vi.spyOn(verdictsApi, 'giveVerdict').mockRejectedValue(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      const { find, text, wrapper } = await open()

      await find('noise-quiet').trigger('click')
      await flushPromises()

      expect(text('noise-failure')).toContain("Can't reach AresGate.")
      expect(wrapper.findComponent(NoiseCard).emitted('judged')).toBeUndefined()
      expect(find('noise-quiet').attributes('disabled')).toBeUndefined()
    })

    it('holds the other buttons while it is being said', async () => {
      let finish: (value: ReturnType<typeof given>) => void = () => {}
      vi.spyOn(verdictsApi, 'giveVerdict').mockReturnValue(
        new Promise((resolve) => {
          finish = resolve
        }),
      )
      const { find, wrapper } = await open()

      await find('noise-quiet').trigger('click')

      const buttons = wrapper.findAll('[data-test="noise-quiet"]')
      expect(buttons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
      finish(given())
      await flushPromises()
      expect(find('noise-quiet').attributes('disabled')).toBeUndefined()
    })
  })
})
