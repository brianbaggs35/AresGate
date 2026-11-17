import { ApiError } from '@/api/client'
import * as threatIntel from '@/api/threatIntel'
import type { KnownPage, Lookup, SubjectKind } from '@/api/threatIntel'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import {
  CLEAN_LOOKUP,
  GREYNOISE_LOOKUP,
  KEPT_URL,
  MALICIOUS_LOOKUP,
  OTX_LOOKUP,
  RULED_LOOKUP,
  SAFE_RULING,
  knownPage,
} from '@/test/threatIntel'

async function mountKnown(result: KnownPage | Error = knownPage(), kind: SubjectKind = 'ip') {
  const fetch = vi.spyOn(threatIntel, 'fetchKnownThreats')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue(result)
  const mounted = await mountWithPlugins(ThreatKnown, {
    signedIn: 'brian',
    props: { kind, version: 0 },
  })
  await flushPromises()
  const { wrapper } = mounted
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  const rows = () => wrapper.findAll('[data-test="known-row"]')
  const answers = () => wrapper.findAll('[data-test="known-answer"]')
  const reportWindow = () =>
    document.querySelector<HTMLElement>('.v-overlay--active [data-test="threat-report"]')
  return { ...mounted, fetch, find, rows, answers, reportWindow }
}

describe('ThreatKnown', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reads the first page of everything kept', async () => {
    const { fetch } = await mountKnown()

    expect(fetch).toHaveBeenCalledWith({
      kind: 'ip',
      q: '',
      judgement: null,
      limit: 25,
    })
  })

  it('lists each subject with its judgement, what the service said and when it was checked', async () => {
    const { rows, answers, find } = await mountKnown()

    expect(rows().map((row) => row.find('[data-test="known-subject"]').text())).toEqual([
      '93.184.216.34',
      'example.com',
      'login.example.net',
    ])
    expect(rows().map((row) => row.attributes('data-judgement'))).toEqual([
      'malicious',
      'clean',
      'unknown',
    ])
    expect(answers().map((one) => one.find('[data-test="known-tally"]').text())).toEqual([
      '4 of 84 flagged',
      '0 of 82 flagged',
      'No report',
    ])
    expect(answers()[0]?.find('[data-test="known-service"]').text()).toBe('VirusTotal')
    expect(answers()[0]?.find('[data-test="known-checked"]').text()).toMatch(/^Checked \S/)
    expect(answers()[0]?.attributes('aria-label')).toBe(
      '93.184.216.34, VirusTotal: Malicious, 4 of 84 flagged. Open its report.',
    )
    expect(find('known-more').exists()).toBe(false)
  })

  it('puts what each service said of one subject in one row, the answer that matters most first', async () => {
    const { rows, answers, wrapper } = await mountKnown(
      knownPage({
        total: 3,
        items: [
          GREYNOISE_LOOKUP,
          { ...CLEAN_LOOKUP, kind: 'ip', subject: '93.184.216.34' },
          OTX_LOOKUP,
        ],
        counts: { malicious: 1, suspicious: 1, clean: 1, unknown: 0 },
      }),
    )

    expect(rows()).toHaveLength(1)
    expect(rows()[0]?.attributes('data-judgement')).toBe('malicious')
    expect(answers().map((one) => one.attributes('data-provider'))).toEqual([
      'greynoise',
      'virustotal',
      'otx',
    ])
    expect(wrapper.find('[data-test="threat-known"]').text()).toContain(
      'Every answer the services gave about IP addresses',
    )
  })

  it('names the kind it lists in what it says', async () => {
    const { wrapper } = await mountKnown(knownPage(), 'domain')

    expect(wrapper.find('[data-test="threat-known"]').text()).toContain(
      'about domains is kept here',
    )
  })

  it('opens the answer of the service that was picked, and asks that service again, not another', async () => {
    const search = vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(OTX_LOOKUP)
    const { answers, find, reportWindow } = await mountKnown(
      knownPage({
        total: 2,
        items: [MALICIOUS_LOOKUP, OTX_LOOKUP],
        counts: { malicious: 2, suspicious: 0, clean: 0, unknown: 0 },
      }),
    )
    await answers()[1]?.trigger('click')
    await flushPromises()
    reportWindow()?.querySelector<HTMLElement>('[data-test="report-refresh"]')?.click()
    await flushPromises()

    expect(search).toHaveBeenCalledWith('otx', '93.184.216.34', 'a-security-token', true, 'ip')
    expect(find('known-problem').exists()).toBe(false)
  })

  it('marks an answer that is due to be checked again', async () => {
    const { answers } = await mountKnown()

    expect(answers().map((row) => row.find('[data-test="known-stale"]').exists())).toEqual([
      false,
      false,
      true,
    ])
  })

  it('counts what is kept of each judgement on its filters', async () => {
    const { find } = await mountKnown()

    expect(find('known-filter-all').text()).toBe('All 3')
    expect(find('known-filter-malicious').text()).toBe('Malicious 1')
    expect(find('known-filter-suspicious').text()).toBe('Suspicious 0')
    expect(find('known-filter-clean').text()).toBe('Clean 1')
    expect(find('known-filter-unknown').text()).toBe('No report 1')
    expect(find('known-filter-all').attributes('aria-pressed')).toBe('true')
  })

  it('narrows the list to one judgement, and back to all', async () => {
    const { fetch, find } = await mountKnown()

    await find('known-filter-malicious').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: '',
      judgement: 'malicious',
      limit: 25,
    })
    expect(find('known-filter-malicious').attributes('aria-pressed')).toBe('true')
    expect(find('known-filter-all').attributes('aria-pressed')).toBe('false')

    await find('known-filter-all').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: '',
      judgement: null,
      limit: 25,
    })
  })

  it('finds what is typed, without its spaces, and everything again once it is cleared', async () => {
    const { wrapper, fetch, find } = await mountKnown()
    await wrapper.find<HTMLInputElement>('[data-test="known-text"] input').setValue('  example ')

    await find('known-form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: 'example',
      judgement: null,
      limit: 25,
    })

    await wrapper.find('[data-test="known-text"] .v-field__clearable .v-icon').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: '',
      judgement: null,
      limit: 25,
    })
  })

  it('says when nothing kept matches, and keeps the search and filters there', async () => {
    const { fetch, find } = await mountKnown()
    fetch.mockResolvedValue(
      knownPage({
        total: 0,
        items: [],
        counts: { malicious: 0, suspicious: 0, clean: 0, unknown: 0 },
      }),
    )
    await find('known-filter-suspicious').trigger('click')
    await flushPromises()

    expect(find('known-none').text()).toBe('Nothing kept matches.')
    expect(find('known-form').exists()).toBe(true)
    expect(find('known-empty').exists()).toBe(false)
  })

  it('says so when nothing is kept at all', async () => {
    const { find } = await mountKnown(
      knownPage({
        total: 0,
        items: [],
        counts: { malicious: 0, suspicious: 0, clean: 0, unknown: 0 },
      }),
    )

    expect(find('known-empty').text()).toContain('Nothing is kept yet')
    expect(find('known-empty').text()).toContain('from a lookup about an incident')
    expect(find('known-form').exists()).toBe(false)
  })

  it.each([
    ['domain', 'a domain'],
    ['url', 'a web address'],
  ] as const)(
    'says a %s is kept only once someone searches for one, since none is looked up by itself',
    async (kind, about) => {
      const { find } = await mountKnown(
        knownPage({
          total: 0,
          items: [],
          counts: { malicious: 0, suspicious: 0, clean: 0, unknown: 0 },
        }),
        kind,
      )

      const text = find('known-empty').text()
      expect(text).toContain(`AresGate asks about ${about} only when you search for one`)
      expect(text).not.toContain('lookup about an incident')
    },
  )

  it('shows more of a long list on request', async () => {
    const { fetch, find } = await mountKnown(knownPage({ total: 40 }))

    expect(find('known-more').text()).toBe('Show more (37 left)')
    await find('known-more').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: '',
      judgement: null,
      limit: 50,
    })
  })

  it('starts from the first page again when the filter changes', async () => {
    const { fetch, find } = await mountKnown(knownPage({ total: 40 }))
    await find('known-more').trigger('click')
    await flushPromises()

    await find('known-filter-clean').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      kind: 'ip',
      q: '',
      judgement: 'clean',
      limit: 25,
    })
  })

  it('reads the list again when the page says something was answered', async () => {
    const { wrapper, fetch } = await mountKnown()

    await wrapper.setProps({ version: 1 })
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows a placeholder while the list is on its way', async () => {
    vi.spyOn(threatIntel, 'fetchKnownThreats').mockReturnValue(new Promise(() => undefined))
    const { wrapper } = await mountWithPlugins(ThreatKnown, {
      signedIn: 'brian',
      props: { kind: 'ip' },
    })

    expect(wrapper.find('[data-test="known-loading"]').exists()).toBe(true)
  })

  it('says the list did not load, and tries again', async () => {
    const { fetch, find, rows } = await mountKnown(
      new ApiError(503, 'Service unavailable', 'unavailable'),
    )
    expect(find('threat-known-error').exists()).toBe(true)
    fetch.mockResolvedValue(knownPage())

    await find('threat-known-retry').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
  })

  it('keeps the list and says what went wrong when reading it again fails', async () => {
    const { fetch, find, rows } = await mountKnown()
    fetch.mockRejectedValue(new ApiError(503, 'Service unavailable', 'unavailable'))

    await find('known-filter-clean').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
    expect(find('known-problem').text()).toBe('Service unavailable')
  })

  it('opens an answer as the report it was', async () => {
    const { answers, reportWindow } = await mountKnown()

    await answers()[0]?.trigger('click')
    await flushPromises()

    expect(reportWindow()?.querySelector('[data-test="report-subject"]')?.textContent).toBe(
      '93.184.216.34',
    )
  })

  it('closes the report when the report asks to', async () => {
    const { wrapper, answers, reportWindow } = await mountKnown()
    await answers()[0]?.trigger('click')
    await flushPromises()

    wrapper.findComponent(ThreatReportDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(reportWindow()).toBeNull()
  })

  it('asks VirusTotal again about an open answer, shows the newer one and reads the list again', async () => {
    const newer: Lookup = { ...MALICIOUS_LOOKUP, checks: 2 }
    const search = vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(newer)
    const { wrapper, fetch, answers, reportWindow } = await mountKnown()
    await answers()[0]?.trigger('click')

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(search).toHaveBeenCalledWith(
      'virustotal',
      '93.184.216.34',
      'a-security-token',
      true,
      'ip',
    )
    expect(reportWindow()?.querySelector('[data-test="report-checks"]')?.textContent).toBe(
      '2 times',
    )
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('refused')).toBeUndefined()
  })

  it('tells the page when a limit held the check, so that the limit shows', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue({
      ...MALICIOUS_LOOKUP,
      cached: true,
      notice: "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
    })
    const { wrapper, answers } = await mountKnown()
    await answers()[0]?.trigger('click')

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(wrapper.emitted('refused')).toHaveLength(1)
  })

  it('closes the report and says why when the check fails', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockRejectedValue(
      new ApiError(502, 'VirusTotal answered HTTP 500.', 'bad_gateway'),
    )
    const { wrapper, find, answers } = await mountKnown()
    await answers()[1]?.trigger('click')

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(find('known-problem').text()).toBe('VirusTotal answered HTTP 500.')
    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(wrapper.emitted('refused')).toHaveLength(1)

    await answers()[1]?.trigger('click')
    expect(find('known-problem').exists()).toBe(false)
  })

  it('checks again once at a time', async () => {
    let answer: (lookup: Lookup) => void = () => undefined
    const search = vi
      .spyOn(threatIntel, 'searchThreatIntel')
      .mockImplementation(() => new Promise((resolve) => (answer = resolve)))
    const { wrapper, answers } = await mountKnown()
    await answers()[1]?.trigger('click')
    const report = wrapper.findComponent(ThreatReportDialog)

    report.vm.$emit('refresh')
    await flushPromises()
    report.vm.$emit('refresh')
    await flushPromises()

    expect(search).toHaveBeenCalledTimes(1)
    expect(report.props('busy')).toBe(true)
    answer(CLEAN_LOOKUP)
    await flushPromises()
    expect(report.props('busy')).toBe(false)
  })

  it('offers no check for a kept web address', async () => {
    const { answers, reportWindow } = await mountKnown()

    await answers()[2]?.trigger('click')
    await flushPromises()

    expect(reportWindow()?.querySelector('[data-test="report-subject"]')?.textContent).toBe(
      KEPT_URL.subject,
    )
    expect(reportWindow()?.querySelector('[data-test="report-refresh"]')).toBeNull()
  })

  it('says what the owner ruled of a subject, which comes to the ruling and not what VirusTotal said', async () => {
    const { rows, answers } = await mountKnown(
      knownPage({
        items: [
          { ...RULED_LOOKUP, cached: true },
          { ...CLEAN_LOOKUP, cached: true },
        ],
      }),
    )

    expect(rows()[0]?.attributes('data-judgement')).toBe('clean')
    expect(rows()[0]?.find('[data-test="known-ruled"]').text()).toBe('Ruled by you')
    expect(answers()[0]?.find('[data-test="known-tally"]').text()).toBe('4 of 84 flagged')
    expect(answers()[0]?.attributes('aria-label')).toBe(
      '93.184.216.34, VirusTotal: Clean, 4 of 84 flagged. You ruled it safe. Open its report.',
    )
    expect(rows()[1]?.find('[data-test="known-ruled"]').exists()).toBe(false)
  })

  it('shows an answer as ruled when its report was ruled, and tells the page to read again', async () => {
    const { wrapper, answers } = await mountKnown()
    await answers()[0]?.trigger('click')
    await flushPromises()

    wrapper.findComponent(ThreatReportDialog).vm.$emit('ruled', SAFE_RULING)
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').judgement).toBe('clean')
    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').ruling).toEqual(SAFE_RULING)
    expect(wrapper.emitted('ruled')).toHaveLength(1)

    wrapper.findComponent(ThreatReportDialog).vm.$emit('ruled', null)
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('lookup').judgement).toBe('malicious')
    expect(wrapper.emitted('ruled')).toHaveLength(2)
  })
})
