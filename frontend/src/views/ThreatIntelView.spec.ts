import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { IntegrationSummary } from '@/api/integrations'
import * as catalogApi from '@/api/threatCatalog'
import * as threatIntelApi from '@/api/threatIntel'
import ThreatCves from '@/components/ThreatCves.vue'
import ThreatDevices from '@/components/ThreatDevices.vue'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatRulings from '@/components/ThreatRulings.vue'
import { summary } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { cvePage, deviceIntelPage } from '@/test/threatCatalog'
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
  const rulings = vi.spyOn(threatIntelApi, 'fetchRulings').mockResolvedValue({ items: [] })
  const cves = vi.spyOn(catalogApi, 'fetchCves').mockResolvedValue(cvePage())
  const devices = vi.spyOn(catalogApi, 'fetchDeviceIntel').mockResolvedValue(deviceIntelPage())
  const mounted = await mountWithPlugins(ThreatIntelView, { signedIn: 'brian' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetch, known, rulings, cves, devices, find }
}

/** The integrations, with AlienVault OTX and GreyNoise as given, and VirusTotal not connected. */
function listOf(otx: IntegrationSummary['status'], greynoise: IntegrationSummary['status']) {
  return [
    ...listWith('not_connected'),
    summary({ key: 'otx', name: 'AlienVault OTX', status: otx }),
    summary({ key: 'greynoise', name: 'GreyNoise', status: greynoise }),
  ]
}

describe('ThreatIntelView', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('has a tab for each kind of threat intelligence, and opens IP addresses first', async () => {
    const { wrapper } = await open(listOf('connected', 'connected'))

    expect(wrapper.findAll('[role="tab"]').map((tab) => tab.text())).toEqual([
      'IP addresses',
      'Domains',
      'Web addresses',
      'CVEs',
      'Devices',
    ])
    expect(wrapper.findComponent(ThreatLookup).props('kind')).toBe('ip')
    expect(wrapper.findComponent(ThreatKnown).props('kind')).toBe('ip')
  })

  it('searches every connected service that answers about the kind of the open tab', async () => {
    const { wrapper, find } = await open(listOf('connected', 'not_connected'))

    // VirusTotal is not connected in this list.
    expect(wrapper.findComponent(ThreatLookup).props('services')).toEqual([
      { key: 'otx', pause: null },
    ])
    expect(wrapper.findComponent(ThreatLookup).props('missing')).toEqual([
      'virustotal',
      'greynoise',
    ])

    await find('threat-tab-url').trigger('click')
    await flushPromises()

    // Only VirusTotal answers about web addresses.
    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').text()).toContain('VirusTotal answers searches')
  })

  it('shows a service in every tab it answers about', async () => {
    const { wrapper, find } = await open(listWith('connected'))
    const asked = () =>
      wrapper
        .findComponent(ThreatLookup)
        .props('services')
        .map((one: { key: string }) => one.key)

    expect(asked()).toEqual(['virustotal'])
    await find('threat-tab-domain').trigger('click')
    await flushPromises()
    expect(asked()).toEqual(['virustotal'])
    expect(wrapper.findComponent(ThreatLookup).props('kind')).toBe('domain')
    await find('threat-tab-url').trigger('click')
    await flushPromises()
    expect(asked()).toEqual(['virustotal'])
    expect(wrapper.findComponent(ThreatLookup).props('kind')).toBe('url')
  })

  it('lists what is kept of the kind of the tab that is open', async () => {
    const { find, known } = await open(listOf('connected', 'connected'))

    await find('threat-tab-domain').trigger('click')
    await flushPromises()

    expect(known).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'domain' }))
    expect(find('threat-intelligence-setup').exists()).toBe(false)
  })

  it('lists the CVEs NVD answered about on the CVE tab, with no search', async () => {
    const { wrapper, find, cves } = await open(listWith('connected'))

    await find('threat-tab-cve').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(ThreatCves).exists()).toBe(true)
    expect(cves).toHaveBeenCalledTimes(1)
    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-known').exists()).toBe(false)
    expect(find('threat-intelligence-setup').exists()).toBe(false)
  })

  it('lists what Fingerbank made of each device on the Devices tab', async () => {
    const { wrapper, find, devices } = await open(listWith('not_connected'))

    await find('threat-tab-device').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(ThreatDevices).exists()).toBe(true)
    expect(wrapper.findComponent(ThreatCves).exists()).toBe(false)
    expect(devices).toHaveBeenCalledTimes(1)
  })

  it('reads the CVEs and the devices again after something is ruled or answered', async () => {
    const { wrapper, find, cves } = await open(listWith('connected'))
    await find('threat-tab-cve').trigger('click')
    await flushPromises()

    wrapper.findComponent(ThreatRulings).vm.$emit('changed')
    await flushPromises()

    expect(cves).toHaveBeenCalledTimes(2)
  })

  it("tells each service's lookup its own limit, not another's", async () => {
    const list = listOf('connected', 'not_connected').map((item) =>
      item.key === 'otx'
        ? { ...item, pause: { until: '2099-01-01T00:00:00Z', daily: true } }
        : item,
    )
    const { find } = await open(list)

    expect(find('threat-notice').text()).toContain("AlienVault OTX's daily limit is reached.")
  })

  it('says which services answer, and links to the Integrations page, while none of them is connected', async () => {
    const { find, wrapper } = await open(listWith('not_connected'))
    await find('threat-tab-url').trigger('click')
    await flushPromises()

    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').text()).toContain(
      'VirusTotal answers searches for a web address',
    )
    expect(find('threat-intelligence-setup').text()).toContain(
      'Connect VirusTotal on the Integrations page',
    )
    const button = wrapper.find('[data-test="threat-intelligence-set-up"]')
    expect(button.text()).toBe('Go to Integrations')
    expect(button.attributes('href')).toBe('/integrations')
  })

  it('says to connect one of them where several answer', async () => {
    const { find } = await open(listOf('not_connected', 'not_connected'))

    expect(find('threat-intelligence-setup').text()).toContain(
      'VirusTotal, AlienVault OTX, and GreyNoise answer searches for an IP address',
    )
    expect(find('threat-intelligence-setup').text()).toContain('Connect one of them')
  })

  it('says the same while a service is set up but its connection is not tested', async () => {
    const { find } = await open(listWith('untested'))

    expect(find('threat-lookup').exists()).toBe(false)
    expect(find('threat-intelligence-setup').exists()).toBe(true)
  })

  it('says the same when the services are not in the list at all', async () => {
    const { find } = await open([
      summary({ key: 'opnsense', name: 'OPNsense', status: 'connected' }),
    ])

    expect(find('threat-intelligence-setup').exists()).toBe(true)
  })

  it('offers the search once a service that answers is connected', async () => {
    const { find } = await open(listWith('connected'))

    expect(find('threat-lookup').exists()).toBe(true)
    expect(find('threat-intelligence-setup').exists()).toBe(false)
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

  it('asks for the list again when a search is refused, so that a limit a service set shows', async () => {
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

  it('lists what the owner ruled, with or without a service connected', async () => {
    const connected = await open(listWith('connected'))
    expect(connected.find('threat-rulings').exists()).toBe(true)
    connected.wrapper.unmount()

    const without = await open(listWith('not_connected'))
    expect(without.find('threat-rulings').exists()).toBe(true)
  })

  it('reads the rulings and what is kept again after an answer is ruled', async () => {
    const { wrapper, known, rulings } = await open(listWith('connected'))
    expect(rulings).toHaveBeenCalledTimes(1)

    wrapper.findComponent(ThreatKnown).vm.$emit('ruled')
    await flushPromises()

    expect(rulings).toHaveBeenCalledTimes(2)
    expect(known).toHaveBeenCalledTimes(2)
  })

  it('reads the answers again after something is ruled in the list of rulings', async () => {
    const { wrapper, known } = await open(listWith('connected'))

    wrapper.findComponent(ThreatRulings).vm.$emit('changed')
    await flushPromises()

    expect(known).toHaveBeenCalledTimes(2)
  })

  it('reads what is kept after a search result is ruled', async () => {
    const { wrapper, known } = await open(listWith('connected'))

    wrapper.findComponent(ThreatLookup).vm.$emit('ruled')
    await flushPromises()

    expect(known).toHaveBeenCalledTimes(2)
  })

  it('lists no rulings while the page is loading or did not load', async () => {
    const { find } = await open(new ApiError(503, 'Service unavailable', 'unavailable'))

    expect(find('threat-rulings').exists()).toBe(false)
  })
})
