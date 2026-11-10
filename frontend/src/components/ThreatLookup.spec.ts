import { ApiError } from '@/api/client'
import type { Pause } from '@/api/integrations'
import * as threatIntel from '@/api/threatIntel'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { CLEAN_LOOKUP } from '@/test/threatIntel'

const CLEAN = CLEAN_LOOKUP

async function mountLookup(pause: Pause | null = null) {
  const mounted = await mountWithPlugins(ThreatLookup, { signedIn: 'brian', props: { pause } })
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

  it('searches what is typed without its spaces, with the security token, and opens the report', async () => {
    const search = vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(CLEAN)
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('  example.com  ')

    await submit()

    expect(search).toHaveBeenCalledWith('example.com', 'a-security-token', false)
    expect(wrapper.find('[data-test="threat-last-subject"]').text()).toBe('example.com')
    expect(reportWindow()).not.toBeNull()
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
  })

  it('searches when the search button is pressed', async () => {
    const search = vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(CLEAN)
    const { wrapper, type } = await mountLookup()
    await type('example.com')

    await wrapper.find('[data-test="threat-search"]').trigger('click')
    await flushPromises()

    expect(search).toHaveBeenCalledTimes(1)
  })

  it('asks nothing for a search that is only spaces', async () => {
    const search = vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(CLEAN)
    const { type, submit, reportWindow } = await mountLookup()
    await type('   ')

    await submit()

    expect(search).not.toHaveBeenCalled()
    expect(reportWindow()).toBeNull()
  })

  it('says why a search was refused, and how long to wait, without a failure or a report, and asks for the limits again', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockRejectedValue(
      new ApiError(
        429,
        "VirusTotal's limit on searches is reached. Try again in 5 seconds.",
        'rate_limited',
      ),
    )
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('203.0.113.7')

    await submit()

    expect(wrapper.find('[data-test="threat-notice"]').text()).toContain('Try again in 5 seconds.')
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
    expect(reportWindow()).toBeNull()
    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(false)
    expect(wrapper.emitted('refused')).toHaveLength(1)
  })

  it('says that an answer arrived, so the page reads what is kept again', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(CLEAN)
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')

    await submit()

    expect(wrapper.emitted('answered')).toHaveLength(1)
    expect(wrapper.emitted('refused')).toBeUndefined()
  })

  it('shows the answer kept when a limit holds the search, and asks for the limits again', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue({
      ...CLEAN,
      cached: true,
      stale: true,
      notice: "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
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

  it('asks VirusTotal again about the last search from the report, and shows the newer answer', async () => {
    const search = vi
      .spyOn(threatIntel, 'searchThreatIntel')
      .mockResolvedValueOnce({ ...CLEAN, cached: true })
      .mockResolvedValueOnce({ ...CLEAN, checks: 2 })
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')
    await submit()

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(search).toHaveBeenLastCalledWith('example.com', 'a-security-token', true)
    expect(reportWindow()?.querySelector('[data-test="report-checks"]')?.textContent).toBe(
      '2 times',
    )
    expect(wrapper.emitted('answered')).toHaveLength(2)
  })

  it('closes the report and says why when checking again is refused', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel')
      .mockResolvedValueOnce({ ...CLEAN, cached: true })
      .mockRejectedValueOnce(new ApiError(502, 'VirusTotal answered HTTP 500.', 'bad_gateway'))
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')
    await submit()

    wrapper.findComponent(ThreatReportDialog).vm.$emit('refresh')
    await flushPromises()

    expect(wrapper.find('[data-test="threat-problem"]').text()).toBe(
      'VirusTotal answered HTTP 500.',
    )
    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(wrapper.find('[data-test="threat-last-subject"]').text()).toBe('example.com')
  })

  it('checks again once at a time', async () => {
    let answer: (lookup: typeof CLEAN) => void = () => undefined
    const search = vi
      .spyOn(threatIntel, 'searchThreatIntel')
      .mockResolvedValueOnce(CLEAN)
      .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')
    await submit()
    const report = wrapper.findComponent(ThreatReportDialog)

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
    vi.spyOn(threatIntel, 'searchThreatIntel').mockRejectedValue(new Error('boom'))
    const { wrapper, type, submit } = await mountLookup()
    await type('example.com')

    await submit()

    expect(wrapper.find('[data-test="threat-problem"]').text()).toMatch(/\S/)
    expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(false)
  })

  it("says when VirusTotal's daily limit holds searches, and that this is not a failure", async () => {
    const { wrapper } = await mountLookup({ until: '2099-01-01T00:00:00Z', daily: true })

    expect(wrapper.find('[data-test="threat-notice"]').text()).toBe(
      "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
    )
    expect(wrapper.find('[data-test="threat-problem"]').exists()).toBe(false)
  })

  it('says when a minute of waiting holds searches, in UTC', async () => {
    const { wrapper } = await mountLookup({ until: '2099-01-01T12:01:00Z', daily: false })

    expect(wrapper.find('[data-test="threat-notice"]').text()).toBe(
      'VirusTotal asked for fewer requests. Searches resume at 12:01 UTC.',
    )
  })

  it('stops saying so once the limit has lifted', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    try {
      const until = new Date(Date.now() + 60_000).toISOString()
      const { wrapper } = await mountLookup({ until, daily: false })
      expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(true)

      vi.advanceTimersByTime(90_000)
      await flushPromises()

      expect(wrapper.find('[data-test="threat-notice"]').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps the last search one click away once its report is closed', async () => {
    vi.spyOn(threatIntel, 'searchThreatIntel').mockResolvedValue(CLEAN)
    const { wrapper, type, submit, reportWindow } = await mountLookup()
    await type('example.com')
    await submit()
    reportWindow()?.querySelector<HTMLElement>('[data-test="report-done"]')?.click()
    await flushPromises()

    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(false)
    expect(wrapper.find('[data-test="threat-last"]').exists()).toBe(true)

    await wrapper.find('[data-test="threat-reopen"]').trigger('click')

    expect(wrapper.findComponent(ThreatReportDialog).props('modelValue')).toBe(true)
  })
})
