import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { IntegrationSummary } from '@/api/integrations'
import ThreatLookup from '@/components/ThreatLookup.vue'
import { summary } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'
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
  const mounted = await mountWithPlugins(ThreatIntelView, { signedIn: 'brian' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetch, find }
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

  it('says what to set up, and links to VirusTotal, while it is not connected', async () => {
    const { find, wrapper } = await open(listWith('not_connected'))

    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').text()).toContain("VirusTotal isn't set up yet")
    expect(wrapper.find('a[href="/integrations/virustotal"]').exists()).toBe(true)
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
})
