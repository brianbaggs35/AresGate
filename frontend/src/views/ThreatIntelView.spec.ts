import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { IntegrationSummary } from '@/api/integrations'
import * as threatIntelApi from '@/api/threatIntel'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import { summary } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { knownPage } from '@/test/threatIntel'
import ThreatIntelView from '@/views/ThreatIntelView.vue'

/** The integrations, with VirusTotal in the given state. */
function listWith(
  status: IntegrationSummary['status'],
  virustotal: Partial<IntegrationSummary> = {},
): IntegrationSummary[] {
  return [
    summary({ key: 'opnsense', name: 'OPNsense', status: 'connected' }),
    summary({ key: 'virustotal', name: 'VirusTotal', status, ...virustotal }),
  ]
}

async function open(result: IntegrationSummary[] | Error) {
  const fetch = vi.spyOn(integrationsApi, 'fetchIntegrations')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue(result)
  const known = vi.spyOn(threatIntelApi, 'fetchKnownThreats').mockResolvedValue(knownPage())
  const mounted = await mountWithPlugins(ThreatIntelView, { signedIn: 'brian' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetch, known, find }
}

describe('ThreatIntelView', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('offers the lookup once VirusTotal is connected and its connection is tested', async () => {
    const { find } = await open(listWith('connected'))

    expect(find('threat-lookup').exists()).toBe(true)
    expect(find('threat-intelligence-setup').exists()).toBe(false)
  })

  it('says an integration is needed, and links to the Integrations page, while none is connected', async () => {
    const { find, wrapper } = await open(listWith('not_connected'))

    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').text()).toContain(
      'needs at least one threat intelligence integration connected',
    )
    const button = wrapper.find('[data-test="threat-intelligence-set-up"]')
    expect(button.text()).toBe('Go to Integrations')
    expect(button.attributes('href')).toBe('/integrations')
  })

  it('says the same while VirusTotal is set up but its connection is not tested', async () => {
    const { find } = await open(listWith('untested'))

    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').exists()).toBe(true)
  })

  it('says the same when VirusTotal is not in the list at all', async () => {
    const { find } = await open([
      summary({ key: 'opnsense', name: 'OPNsense', status: 'connected' }),
    ])

    expect(find('threat-intelligence-setup').exists()).toBe(true)
  })

  it('says the list did not load, and tries again', async () => {
    const { find, fetch } = await open(new ApiError(500, 'The integrations could not be read.'))

    expect(find('threat-intelligence-error').exists()).toBe(true)
    expect(find('threat-lookup').exists()).toBe(false)

    await find('threat-intelligence-retry').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows a placeholder while the list is on its way', async () => {
    vi.spyOn(integrationsApi, 'fetchIntegrations').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(ThreatIntelView, { signedIn: 'brian' })
    await flushPromises()

    expect(wrapper.find('[data-test="threat-intelligence-loading"]').exists()).toBe(true)
  })

  it("tells the lookup of VirusTotal's limit, so that it says when searches resume", async () => {
    const { find } = await open(
      listWith('connected', { pause: { until: '2099-01-01T00:00:00Z', daily: true } }),
    )

    expect(find('threat-notice').text()).toContain("VirusTotal's daily limit is reached.")
  })

  it('asks for the list again when a search is refused, so that a limit VirusTotal set shows', async () => {
    const { fetch, wrapper } = await open(listWith('connected'))

    wrapper.findComponent(ThreatLookup).vm.$emit('refused')
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('lists what AresGate has kept, with or without a service connected', async () => {
    const connected = await open(listWith('connected'))
    expect(connected.find('threat-known').exists()).toBe(true)
    connected.wrapper.unmount()

    const without = await open(listWith('not_connected'))
    expect(without.find('threat-known').exists()).toBe(true)
  })

  it('lists nothing kept while the page is loading or did not load', async () => {
    const { find } = await open(new ApiError(503, 'Service unavailable', 'unavailable'))

    expect(find('threat-known').exists()).toBe(false)
  })

  it('reads what is kept again after a search is answered', async () => {
    const { wrapper, known } = await open(listWith('connected'))
    expect(known).toHaveBeenCalledTimes(1)

    wrapper.findComponent(ThreatLookup).vm.$emit('answered')
    await flushPromises()

    expect(known).toHaveBeenCalledTimes(2)
  })

  it('asks for the list again when a check from what is kept is refused', async () => {
    const { wrapper, fetch } = await open(listWith('connected'))

    wrapper.findComponent(ThreatKnown).vm.$emit('refused')
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
