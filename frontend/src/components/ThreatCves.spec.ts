import { ApiError } from '@/api/client'
import * as catalog from '@/api/threatCatalog'
import type { CvePage } from '@/api/threatCatalog'
import ThreatCveDialog from '@/components/ThreatCveDialog.vue'
import ThreatCves from '@/components/ThreatCves.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { EXPLOITED_CVE, cvePage } from '@/test/threatCatalog'

const NONE: CvePage = cvePage({
  total: 0,
  items: [],
  counts: { critical: 0, high: 0, medium: 0, low: 0, unrated: 0, exploited: 0 },
})

async function mountCves(result: CvePage | Error = cvePage()) {
  const fetch = vi.spyOn(catalog, 'fetchCves')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue(result)
  const mounted = await mountWithPlugins(ThreatCves, {
    signedIn: 'brian',
    props: { version: 0 },
  })
  await flushPromises()
  const { wrapper } = mounted
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  const rows = () => wrapper.findAll('[data-test="cves-row"]')
  return { ...mounted, fetch, find, rows }
}

describe('ThreatCves', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reads the first page of every CVE that is kept', async () => {
    const { fetch } = await mountCves()

    expect(fetch).toHaveBeenCalledWith({ q: '', rating: null, exploited: false, limit: 25 })
  })

  it('lists each CVE with its rating, what it is, its score and when NVD was asked', async () => {
    const { rows, find } = await mountCves()

    expect(rows().map((row) => row.find('[data-test="cves-id"]').text())).toEqual([
      'CVE-2024-3400',
      'CVE-2023-1234',
      'CVE-2026-9999',
    ])
    expect(rows().map((row) => row.attributes('data-rating'))).toEqual([
      'critical',
      'medium',
      'unrated',
    ])
    expect(rows()[0]?.find('[data-test="severity"]').text()).toBe('Critical')
    expect(rows()[0]?.find('[data-test="cves-score"]').text()).toBe('CVSS 10.0')
    expect(rows()[0]?.find('[data-test="cves-description"]').text()).toContain('command injection')
    expect(rows()[0]?.find('[data-test="cves-published"]').text()).toMatch(/^Published \S/)
    expect(rows()[0]?.find('[data-test="cves-checked"]').text()).toMatch(/^Asked \S/)
    expect(rows()[0]?.attributes('aria-label')).toBe(
      'CVE-2024-3400, Critical, 10, exploited in the wild. Open its report.',
    )
    expect(find('cves-more').exists()).toBe(false)
  })

  it('marks a CVE CISA lists as exploited, and leaves out what NVD did not say', async () => {
    const { rows } = await mountCves()

    expect(rows().map((row) => row.find('[data-test="cves-exploited"]').exists())).toEqual([
      true,
      false,
      false,
    ])
    expect(rows()[1]?.find('[data-test="cves-description"]').exists()).toBe(false)
    expect(rows()[2]?.find('[data-test="cves-score"]').exists()).toBe(false)
    expect(rows()[2]?.find('[data-test="cves-published"]').exists()).toBe(false)
    expect(rows()[1]?.attributes('aria-label')).toBe('CVE-2023-1234, Medium, 5.4. Open its report.')
  })

  it('says a CVE is not scored, or that NVD does not know it', async () => {
    const { rows } = await mountCves(
      cvePage({
        items: [
          { ...EXPLOITED_CVE, rating: 'unrated', score: null },
          { ...EXPLOITED_CVE, cve_id: 'CVE-2026-9999', rating: 'unrated', state: 'unknown' },
        ],
      }),
    )

    expect(rows().map((row) => row.find('[data-test="cves-unrated"]').text())).toEqual([
      'Not scored',
      'Unknown to NVD',
    ])
    expect(rows()[0]?.attributes('aria-label')).toBe(
      'CVE-2024-3400, not scored, exploited in the wild. Open its report.',
    )
  })

  it('counts what is kept of each rating, and of what is exploited, on its filters', async () => {
    const { find } = await mountCves()

    expect(find('cves-filter-all').text()).toBe('All 3')
    expect(find('cves-filter-critical').text()).toBe('Critical 1')
    expect(find('cves-filter-high').text()).toBe('High 0')
    expect(find('cves-filter-medium').text()).toBe('Medium 1')
    expect(find('cves-filter-low').text()).toBe('Low 0')
    expect(find('cves-filter-unrated').text()).toBe('Not scored 1')
    expect(find('cves-filter-exploited').text()).toBe('Exploited in the wild 1')
    expect(find('cves-filter-all').attributes('aria-pressed')).toBe('true')
  })

  it('narrows the list to one rating, and back to all', async () => {
    const { fetch, find } = await mountCves()

    await find('cves-filter-critical').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      q: '',
      rating: 'critical',
      exploited: false,
      limit: 25,
    })
    expect(find('cves-filter-critical').attributes('aria-pressed')).toBe('true')
    expect(find('cves-filter-all').attributes('aria-pressed')).toBe('false')

    await find('cves-filter-all').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: null, exploited: false, limit: 25 })
  })

  it('narrows the list to what is exploited in the wild, and back', async () => {
    const { fetch, find } = await mountCves()

    await find('cves-filter-exploited').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: null, exploited: true, limit: 25 })
    expect(find('cves-filter-exploited').attributes('aria-pressed')).toBe('true')

    await find('cves-filter-exploited').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: null, exploited: false, limit: 25 })
  })

  it('finds what is typed, without its spaces, and everything again once it is cleared', async () => {
    const { wrapper, fetch, find } = await mountCves()
    await wrapper.find<HTMLInputElement>('[data-test="cves-text"] input').setValue('  CWE-77 ')

    await find('cves-form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({
      q: 'CWE-77',
      rating: null,
      exploited: false,
      limit: 25,
    })

    await wrapper.find('[data-test="cves-text"] .v-field__clearable .v-icon').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: null, exploited: false, limit: 25 })
  })

  it('says when nothing kept matches, and keeps the search and filters there', async () => {
    const { fetch, find } = await mountCves()
    fetch.mockResolvedValue(NONE)
    await find('cves-filter-low').trigger('click')
    await flushPromises()

    expect(find('cves-none').text()).toBe('Nothing kept matches.')
    expect(find('cves-form').exists()).toBe(true)
    expect(find('cves-empty').exists()).toBe(false)
  })

  it('says how a CVE gets here when none is kept at all, with a way to connect NVD', async () => {
    const { find } = await mountCves(NONE)

    expect(find('cves-empty').text()).toContain('No CVEs yet')
    expect(find('cves-empty').text()).toContain('names a CVE')
    expect(find('cves-set-up').attributes('href')).toBe('/integrations')
    expect(find('cves-form').exists()).toBe(false)
  })

  it('shows more of a long list on request, and starts over when the filter changes', async () => {
    const { fetch, find } = await mountCves(cvePage({ total: 40 }))

    expect(find('cves-more').text()).toBe('Show more (37 left)')
    await find('cves-more').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: null, exploited: false, limit: 50 })

    await find('cves-filter-medium').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith({ q: '', rating: 'medium', exploited: false, limit: 25 })
  })

  it('carries the notice NVD asks for under the list', async () => {
    const { find } = await mountCves()

    expect(find('cves-notice').text()).toBe(cvePage().notice)
  })

  it('reads the list again when the page says something was answered', async () => {
    const { wrapper, fetch } = await mountCves()

    await wrapper.setProps({ version: 1 })
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows a placeholder while the list is on its way', async () => {
    vi.spyOn(catalog, 'fetchCves').mockReturnValue(new Promise(() => undefined))
    const { wrapper } = await mountWithPlugins(ThreatCves, { signedIn: 'brian' })

    expect(wrapper.find('[data-test="cves-loading"]').exists()).toBe(true)
  })

  it('says the list did not load, and tries again', async () => {
    const { fetch, find, rows } = await mountCves(
      new ApiError(503, 'Service unavailable', 'unavailable'),
    )
    expect(find('cves-error').exists()).toBe(true)
    fetch.mockResolvedValue(cvePage())

    await find('cves-retry').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
  })

  it('keeps the list and says what went wrong when reading it again fails', async () => {
    const { fetch, find, rows } = await mountCves()
    fetch.mockRejectedValue(new ApiError(503, 'Service unavailable', 'unavailable'))

    await find('cves-filter-medium').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
    expect(find('cves-problem').text()).toBe('Service unavailable')
  })

  it('opens a CVE as its report', async () => {
    const { wrapper, rows } = await mountCves()

    await rows()[0]?.trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(ThreatCveDialog).props('cve').cve_id).toBe('CVE-2024-3400')
    expect(wrapper.findComponent(ThreatCveDialog).props('modelValue')).toBe(true)
    expect(wrapper.findComponent(ThreatCveDialog).props('notice')).toBe(cvePage().notice)
  })

  it('closes the report when the report asks to', async () => {
    const { wrapper, rows } = await mountCves()
    await rows()[0]?.trigger('click')
    await flushPromises()

    wrapper.findComponent(ThreatCveDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(ThreatCveDialog).props('modelValue')).toBe(false)
  })
})
