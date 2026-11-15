import { ApiError } from '@/api/client'
import type { Pause } from '@/api/integrations'
import * as threatIntel from '@/api/threatIntel'
import type { Lookup, Provider, SubjectKind } from '@/api/threatIntel'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import {
  CLEAN_LOOKUP,
  GREYNOISE_LOOKUP,
  MALICIOUS_LOOKUP,
  OTX_LOOKUP,
  SAFE_RULING,
} from '@/test/threatIntel'

const CLEAN = CLEAN_LOOKUP
const ONLY_VIRUSTOTAL = [{ key: 'virustotal' as Provider, pause: null }]

interface Options {
  kind?: SubjectKind
  services?: { key: Provider; pause: Pause | null }[]
  missing?: Provider[]
}

async function mountLookup({
  kind = 'domain',
  services = ONLY_VIRUSTOTAL,
  missing = [],
}: Options = {}) {
  const mounted = await mountWithPlugins(ThreatLookup, {
    signedIn: 'brian',
    props: { kind, services, missing },
  })
  const { wrapper } = mounted
  const type = async (text: string) => {
    await wrapper.find<HTMLInputElement>('[data-test="threat-subject"] input').setValue(text)
  }
  const submit = async () => {
    await wrapper.find('[data-test="threat-form"]').trigger('submit')
    await flushPromises()
  }
  const reportWindow = () =>
    document.querySelector<HTMLElement>('.v-overlay--active [data-test="threat-report"]')
  return { ...mounted, type, submit, reportWindow }
}

/** Each service answers with what it is given: an answer, or the failure it fails with. */
function serviceAnswers(by: Partial<Record<Provider, Lookup | Error>>) {
  return vi.spyOn(threatIntel, 'searchThreatIntel').mockImplementation((provider) => {
    const reply = by[provider]
    return reply instanceof Error ? Promise.reject(reply) : Promise.resolve(reply as Lookup)
  })
}

const LIMIT = new ApiError(
  429,
  'Its limit on searches is reached. Try again in 5 seconds.',
  'rate_limited',
)

const THREE = [
  { key: 'virustotal' as Provider, pause: null },
  { key: 'otx' as Provider, pause: null },
  { key: 'greynoise' as Provider, pause: null },
]

describe('ThreatLookup', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('has nothing to search until something is typed', async () => {
    const { wrapper, type } = await mountLookup()

    expect(wrapper.find('[data-test="threat-search"]').attributes('disabled')).toBeDefined()

    await type('example.com')

    expect(wrapper.find('[data-test="threat-search"]').attributes('disabled')).toBeUndefined()
  })

  it('asks about the kind it was given, naming every service it asks', async () => {
    const { wrapper } = await mountLookup({
      kind: 'ip',
      services: [
        { key: 'virustotal', pause: null },
        { key: 'otx', pause: null },
        { key: 'greynoise', pause: null },
      ],
    })

    const text = wrapper.find('[data-test="threat-lookup"]').text()
    expect(text).toContain('Look up an IP address')
    expect(text).toContain('Ask VirusTotal, AlienVault OTX, and GreyNoise at once.')
    expect(wrapper.find('[data-test="threat-subject"] input').attributes('placeholder')).toBe(
      '203.0.113.7',
    )
  })

  it('asks every connected service at once, with the kind and the security token', async () => {
    const search = serviceAnswers({
      virustotal: { ...MALICIOUS_LOOKUP },
      otx: OTX_LOOKUP,
      greynoise: GREYNOISE_LOOKUP,
    })
    const { wrapper, type, submit, reportWindow } = await mountLookup({
      kind: 'ip',
      services: THREE,
    })
    await type('  93.184.216.34  ')

    await submit()

    expect(search).toHaveBeenCalledTimes(3)
    expect(search).toHaveBeenCalledWith(
      'virustotal',
      '93.184.216.34',
      'a-security-token',
      false,
      'ip',
    )
    expect(search).toHaveBeenCalledWith('otx', '93.184.216.34', 'a-security-token', false, 'ip')
    expect(search).toHaveBeenCalledWith(
      'greynoise',
      '93.184.216.34',
      'a-security-token',
      false,
      'ip',
    )
    expect(wrapper.find('[data-test="threat-last-subject"]').text()).toBe('93.184.216.34')
    // Several answers sit side by side, and the owner picks which to open.
    expect(wrapper.findAll('[data-test="threat-result"]')).toHaveLength(3)
    expect(reportWindow()).toBeNull()
    expect(wrapper.emitted('answered')).toHaveLength(1)
  })

  it('names each answer for its service, and opens the report of the one that is chosen', async () => {
    serviceAnswers({ virustotal: MALICIOUS_LOOKUP, otx: OTX_LOOKUP })
    const { wrapper, type, submit, reportWindow } = await mountLookup({
      kind: 'ip',
      services: THREE.slice(0, 2),
    })
    await type('93.184.216.34')
    await submit()
    const results = wrapper.findAll('[data-test="threat-result"]')

    expect(results[0]?.text()).toContain('VirusTotal')
    expect(results[0]?.text()).toContain('4 of 84 flagged')
    expect(results[1]?.text()).toContain('AlienVault OTX')
    expect(results[1]?.attributes('aria-label')).toBe(
      'View the report of AlienVault OTX: Malicious, 3 pulses',
    )

    await results[1]?.trigger('click')

    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').provider).toBe('otx')
    expect(reportWindow()?.querySelector('[data-test="report-kind"]')?.textContent).toContain(
      'AlienVault OTX',
    )
  })

  it('opens the report at once where only one service answered', async () => {
    serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')

    await submit()

    expect(reportWindow()).not.toBeNull()
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
  })

  it('searches when the search button is pressed', async () => {
    const search = serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type } = await mountLookup()
    await type('example.com')

    await wrapper.find('[data-test="threat-search"]').trigger('click')
    await flushPromises()

    expect(search).toHaveBeenCalledTimes(1)
  })

  it('asks nothing for a search that is only spaces', async () => {
    const search = serviceAnswers({ virustotal: CLEAN })
    const { type, submit, reportWindow } = await mountLookup()
    await type('   ')

    await submit()

    expect(search).not.toHaveBeenCalled()
    expect(reportWindow()).toBeNull()
  })

  it('shows what the services that were not held answered, and says why the held one did not', async () => {
    serviceAnswers({ virustotal: LIMIT, otx: OTX_LOOKUP })
    const { wrapper, type, submit } = await mountLookup({
      kind: 'ip',
      services: THREE.slice(0, 2),
    })
    await type('93.184.216.34')

    await submit()

    expect(wrapper.find('[data-test="threat-notice"]').text()).toBe(
      'VirusTotal: Its limit on searches is reached. Try again in 5 seconds.',
    )
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="threat-result"]')).toHaveLength(1)
    expect(wrapper.emitted('refused')).toHaveLength(1)
    expect(wrapper.emitted('answered')).toHaveLength(1)
  })

  it('says why a search was refused, without a failure or a report, and asks for the limits again', async () => {
    serviceAnswers({ virustotal: LIMIT })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('203.0.113.7')

    await submit()

    expect(wrapper.find('[data-test="threat-notice"]').text()).toContain('Try again in 5 seconds.')
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
    expect(reportWindow()).toBeNull()
    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(false)
    expect(wrapper.emitted('refused')).toHaveLength(1)
    expect(wrapper.emitted('answered')).toBeUndefined()
  })

  it('says that an answer arrived, so the page reads what is kept again', async () => {
    serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')

    await submit()

    expect(wrapper.emitted('answered')).toHaveLength(1)
    expect(wrapper.emitted('refused')).toBeUndefined()
  })

  it('shows the answer kept when a limit holds the search, and asks for the limits again', async () => {
    serviceAnswers({
      virustotal: {
        ...CLEAN,
        cached: true,
        stale: true,
        notice: "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
      },
    })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')

    await submit()

    expect(reportWindow()?.querySelector('[data-test="report-notice"]')?.textContent).toContain(
      "VirusTotal's daily limit is reached.",
    )
    expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(false)
    expect(wrapper.emitted('refused')).toHaveLength(1)
  })

  it('asks the service of the open report again, and only that one, and shows the newer answer', async () => {
    const search = serviceAnswers({ virustotal: { ...CLEAN, cached: true } })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')
    await submit()
    search.mockResolvedValue({ ...CLEAN, checks: 2 })

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(search).toHaveBeenLastCalledWith(
      'virustotal',
      'example.com',
      'a-security-token',
      true,
      'domain',
    )
    expect(search).toHaveBeenCalledTimes(2)
    expect(reportWindow()?.querySelector('[data-test="report-checks"]')?.textContent).toBe(
      '2 times',
    )
    expect(wrapper.emitted('answered')).toHaveLength(2)
  })

  it('leaves what another service answered as it was when one is asked again', async () => {
    const search = serviceAnswers({ virustotal: MALICIOUS_LOOKUP, otx: OTX_LOOKUP })
    const { wrapper, type, submit } = await mountLookup({
      kind: 'ip',
      services: THREE.slice(0, 2),
    })
    await type('93.184.216.34')
    await submit()
    await wrapper.findAll('[data-test="threat-result"]')[1]?.trigger('click')
    search.mockResolvedValue({ ...OTX_LOOKUP, checks: 2 })

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(wrapper.findAll('[data-test="threat-result"]')).toHaveLength(2)
    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').checks).toBe(2)
  })

  it('closes the report and says why when checking again is refused, and keeps what another service said', async () => {
    const search = serviceAnswers({ virustotal: MALICIOUS_LOOKUP, otx: LIMIT })
    const { wrapper, type, submit } = await mountLookup({
      kind: 'ip',
      services: THREE.slice(0, 2),
    })
    await type('93.184.216.34')
    await submit()
    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(true)
    search.mockRejectedValue(new ApiError(502, 'VirusTotal answered HTTP 500.', 'bad_gateway'))

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(wrapper.find('[data-test="threat-problem"]').text()).toBe(
      'VirusTotal answered HTTP 500.',
    )
    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(wrapper.find('[data-test="threat-last-subject"]').text()).toBe('93.184.216.34')
    // The one that was held before is still said to be.
    expect(wrapper.find('[data-test="threat-notice"]').text()).toContain('AlienVault OTX')
  })

  it('checks again once at a time', async () => {
    let answer: (lookup: Lookup) => void = () => undefined
    const search = serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')
    await submit()
    const report = wrapper.findComponent(ThreatReportDialog)
    search.mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))

    report.vm.$emit('refresh')
    await flushPromises()
    report.vm.$emit('refresh')
    await flushPromises()

    expect(report.props('busy')).toBe(true)
    expect(search).toHaveBeenCalledTimes(2)
    answer(CLEAN)
    await flushPromises()
    expect(report.props('busy')).toBe(false)
  })

  it('says something useful when a search fails in a way that was not expected', async () => {
    serviceAnswers({ virustotal: new Error('boom') })
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')

    await submit()

    expect(wrapper.find('[data-test="threat-problem"]').text()).toMatch(/\S/)
    expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(false)
  })

  it('says a subject of another kind is not what this tab searches for', async () => {
    serviceAnswers({
      virustotal: new ApiError(422, 'That is a domain, not an IP address.', 'validation_error'),
    })
    const { wrapper, type, submit } = await mountLookup({ kind: 'ip' })
    await type('example.com')

    await submit()

    expect(wrapper.find('[data-test="threat-problem"]').text()).toBe(
      'That is a domain, not an IP address.',
    )
  })

  it("says when a service's daily limit holds searches, and that this is not a failure", async () => {
    const { wrapper } = await mountLookup({
      services: [{ key: 'virustotal', pause: { until: '2099-01-01T00:00:00Z', daily: true } }],
    })

    expect(wrapper.find('[data-test="threat-notice"]').text()).toBe(
      "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
    )
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
  })

  it("tells each service's limit apart, in UTC", async () => {
    const { wrapper } = await mountLookup({
      kind: 'ip',
      services: [
        { key: 'virustotal', pause: { until: '2099-01-01T00:00:00Z', daily: true } },
        { key: 'otx', pause: { until: '2099-01-01T12:01:00Z', daily: false } },
      ],
    })

    const notices = wrapper.findAll('[data-test="threat-notice"]').map((one) => one.text())
    expect(notices).toEqual([
      "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
      'AlienVault OTX asked for fewer requests. Searches resume at 12:01 UTC.',
    ])
  })

  it('stops saying so once the limit has lifted', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    try {
      const until = new Date(Date.now() + 60_000).toISOString()
      const { wrapper } = await mountLookup({
        services: [{ key: 'virustotal', pause: { until, daily: false } }],
      })
      expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(true)

      vi.advanceTimersByTime(90_000)
      await flushPromises()

      expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('says which services also answer and are not connected, with a way to connect them', async () => {
    const { wrapper } = await mountLookup({ kind: 'ip', missing: ['otx', 'greynoise'] })

    const note = wrapper.find('[data-test="threat-missing"]')
    expect(note.text()).toContain('AlienVault OTX and GreyNoise also answer about an IP address')
    expect(note.text()).toContain('are not connected, so they are not asked.')
    expect(note.find('a').attributes('href')).toBe('/integrations')
  })

  it('says it in the singular for one service', async () => {
    const { wrapper } = await mountLookup({ kind: 'domain', missing: ['otx'] })

    expect(wrapper.find('[data-test="threat-missing"]').text()).toContain(
      'AlienVault OTX also answers about a domain and is not connected, so it is not asked.',
    )
  })

  it('says nothing of services that are all connected', async () => {
    const { wrapper } = await mountLookup()

    expect(wrapper.find('[data-test="threat-missing"]').exists()).toBe(false)
  })

  it("keeps VirusTotal's note about a free key and what is searched for, and no other's", async () => {
    const withIt = await mountLookup()
    expect(withIt.wrapper.find('[data-test="threat-note"]').text()).toContain(
      'VirusTotal allows it for non-commercial use only.',
    )
    withIt.wrapper.unmount()

    const without = await mountLookup({ kind: 'ip', services: [{ key: 'greynoise', pause: null }] })
    expect(without.wrapper.find('[data-test="threat-note"]').exists()).toBe(false)
  })

  it('keeps the last search one click away once its report is closed', async () => {
    serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')
    await submit()
    reportWindow()?.querySelector<HTMLElement>('[data-test="report-done"]')?.click()
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(true)

    await wrapper.find('[data-test="threat-result"]').trigger('click')

    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(true)
  })

  it('shows every answer as the owner ruled it, and tells the page', async () => {
    serviceAnswers({ virustotal: MALICIOUS_LOOKUP, otx: OTX_LOOKUP })
    const { wrapper, type, submit } = await mountLookup({
      kind: 'ip',
      services: THREE.slice(0, 2),
    })
    await type('93.184.216.34')
    await submit()
    await wrapper.find('[data-test="threat-result"]').trigger('click')

    wrapper.findComponent(ThreatReportDialog).vm.$emit('ruled', SAFE_RULING)
    await flushPromises()

    const labels = wrapper
      .findAll('[data-test="threat-result"]')
      .map((one) => one.attributes('aria-label'))
    expect(labels).toEqual([
      'View the report of VirusTotal: Clean, 4 of 84 flagged',
      'View the report of AlienVault OTX: Clean, 3 pulses',
    ])
    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').reported_judgement).toBe(
      'malicious',
    )
    expect(wrapper.emitted('ruled')).toHaveLength(1)

    wrapper.findComponent(ThreatReportDialog).vm.$emit('ruled', null)
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').judgement).toBe('malicious')
  })

  it('forgets the last search when a new one is answered by nobody', async () => {
    const search = serviceAnswers({ virustotal: CLEAN })
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')
    await submit()
    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(true)
    search.mockRejectedValue(LIMIT)

    await type('example.org')
    await submit()

    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(false)
  })
})
