import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { IntegrationSummary } from '@/api/integrations'
import { useSessionStore } from '@/stores/session'
import { summary } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import IntegrationsView from '@/views/IntegrationsView.vue'

const FOUR: IntegrationSummary[] = [
  summary({ key: 'opnsense', name: 'OPNsense', icon: 'firewall', status: 'connected' }),
  summary({ key: 'ntopng', name: 'ntopng' }),
  summary({ key: 'wazuh', name: 'Wazuh', icon: 'alerts', status: 'problem' }),
  summary({ key: 'crowdsec', name: 'CrowdSec', icon: 'threats', status: 'untested' }),
]

async function open(result: IntegrationSummary[] | Error = FOUR) {
  const fetch = vi.spyOn(integrationsApi, 'fetchIntegrations')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue(result)
  const mounted = await mountWithPlugins(IntegrationsView, { signedIn: 'admin' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetch, find }
}

describe('IntegrationsView', () => {
  it('has a card for each integration, each linking to its own page', async () => {
    const { wrapper } = await open()
    const cards = wrapper.findAll('[data-test="integration-name"]')
    expect(cards.map((card) => card.text())).toEqual(['OPNsense', 'ntopng', 'Wazuh', 'CrowdSec'])
    const links = wrapper.findAll('a[href^="/integrations/"]')
    expect(links.map((link) => link.attributes('href'))).toEqual([
      '/integrations/opnsense',
      '/integrations/ntopng',
      '/integrations/wazuh',
      '/integrations/crowdsec',
    ])
  })

  it('goes to an integration’s page when its card is chosen', async () => {
    const { find, router } = await open()
    await find('integration-wazuh').trigger('click')
    // The page is loaded when it is first wanted.
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('integration')
    })
    expect(router.currentRoute.value.params.key).toBe('wazuh')
  })

  it('has a heading, and says what the integrations are for', async () => {
    const { wrapper } = await open()
    expect(wrapper.find('h1').text()).toBe('Integrations')
    expect(wrapper.text()).toContain('It only reads from them')
  })

  it('counts those that are set up', async () => {
    const { find } = await open()
    expect(find('integrations-count').text()).toBe('3 of 4 set up')
  })

  it('counts none when none is', async () => {
    const { find } = await open(FOUR.map((item) => ({ ...item, status: 'not_connected' as const })))
    expect(find('integrations-count').text()).toBe('0 of 4 set up')
  })

  it('shows placeholders while it loads', async () => {
    vi.spyOn(integrationsApi, 'fetchIntegrations').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IntegrationsView, { signedIn: 'admin' })
    expect(wrapper.findAll('.v-skeleton-loader')).toHaveLength(4)
    expect(wrapper.find('[data-test="integrations-count"]').exists()).toBe(false)
  })

  it('says why it could not load, and tries again', async () => {
    const { fetch, find, wrapper } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
    expect(find('integrations-error').text()).toContain("Can't reach AresGate.")
    expect(wrapper.find('[data-test="integrations-list"]').exists()).toBe(false)

    fetch.mockResolvedValue(FOUR)
    await find('integrations-retry').trigger('click')
    await flushPromises()

    expect(find('integrations-error').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="integration-name"]')).toHaveLength(4)
  })

  it('notes that the sign-in is over when the API says so', async () => {
    const { pinia } = await open(new ApiError(401, 'Sign in first.', 'unauthenticated'))
    expect(useSessionStore(pinia).expired).toBe(true)
  })
})
