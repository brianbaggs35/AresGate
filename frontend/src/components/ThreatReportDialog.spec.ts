import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import type { Lookup } from '@/api/threatIntel'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const MALICIOUS: Lookup = {
  kind: 'ip',
  subject: '93.184.216.34',
  judgement: 'malicious',
  checked_at: '2026-11-09T12:00:00Z',
  analysed_at: '2026-11-07T00:00:00Z',
  malicious: 3,
  suspicious: 1,
  harmless: 60,
  undetected: 20,
  reputation: -12,
  categories: ['malware', 'phishing'],
  details: [{ label: 'Owner', value: 'Example Hosting' }],
  link: 'https://www.virustotal.com/gui/ip-address/93.184.216.34',
}

const UNKNOWN: Lookup = {
  ...MALICIOUS,
  judgement: 'unknown',
  malicious: 0,
  suspicious: 0,
  harmless: 0,
  undetected: 0,
  reputation: null,
  analysed_at: null,
  categories: [],
  details: [],
}

/** The report window, open over the page, as a search leaves it. */
async function mountReport(
  lookup: Lookup = MALICIOUS,
  { width, onUpdate = vi.fn() }: { width?: number; onUpdate?: (open: boolean) => void } = {},
) {
  const mounted = await mountWithPlugins(ThreatReportDialog, {
    withApp: true,
    width,
    props: {
      lookup,
      modelValue: true,
      'onUpdate:modelValue': onUpdate,
    },
  })
  await flushPromises()
  const inWindow = (selector: string) =>
    document.querySelector<HTMLElement>(`.v-overlay--active ${selector}`)
  const all = (selector: string) =>
    Array.from(document.querySelectorAll<HTMLElement>(`.v-overlay--active ${selector}`))
  return { ...mounted, inWindow, all, onUpdate }
}

describe('ThreatReportDialog', () => {
  it('names the kind of subject and the subject as it was searched', async () => {
    const { inWindow } = await mountReport()

    expect(inWindow('[data-test="report-kind"]')?.textContent).toContain('IP address')
    expect(inWindow('[data-test="report-subject"]')?.textContent.trim()).toBe('93.184.216.34')
  })

  it('judges a subject that an engine flagged as malicious, with the counts behind it', async () => {
    const { inWindow } = await mountReport()

    const judgement = inWindow('[data-test="report-judgement"]')
    expect(judgement?.dataset.judgement).toBe('malicious')
    expect(judgement?.textContent).toContain('Reported as malicious')
    expect(inWindow('[data-test="report-summary"]')?.textContent.trim()).toBe(
      '3 of 84 engines flagged it as malicious.',
    )
  })

  it('says when engines flagged it as suspicious but none as malicious', async () => {
    const { inWindow } = await mountReport({
      ...MALICIOUS,
      judgement: 'suspicious',
      malicious: 0,
      suspicious: 2,
    })

    expect(inWindow('[data-test="report-judgement"]')?.textContent).toContain(
      'Reported as suspicious',
    )
    expect(inWindow('[data-test="report-summary"]')?.textContent.trim()).toBe(
      '2 of 82 engines flagged it as suspicious.',
    )
  })

  it('says when no engine flagged a subject that has a report', async () => {
    const { inWindow } = await mountReport({
      ...MALICIOUS,
      judgement: 'clean',
      malicious: 0,
      suspicious: 0,
    })

    expect(inWindow('[data-test="report-judgement"]')?.textContent).toContain(
      'No engine flagged it',
    )
    expect(inWindow('[data-test="report-summary"]')?.textContent.trim()).toBe(
      'None of the 80 engines flagged it.',
    )
  })

  it('shows the engines as a bar, with each share sized to its count', async () => {
    const { inWindow, all } = await mountReport()

    const bar = inWindow('[data-test="report-bar"]')
    expect(bar?.getAttribute('aria-hidden')).toBe('true')
    const malicious = inWindow('[data-part="malicious"]') as HTMLElement
    const harmless = inWindow('[data-part="harmless"]') as HTMLElement
    expect(parseFloat(malicious.style.width)).toBeCloseTo((3 / 84) * 100, 5)
    expect(parseFloat(harmless.style.width)).toBeCloseTo((60 / 84) * 100, 5)
    expect(all('[data-test="report-counts"] strong').map((count) => count.textContent)).toEqual([
      '3',
      '1',
      '60',
      '20',
    ])
  })

  it('shows no bar, counts or verdict for a subject with no report', async () => {
    const { inWindow } = await mountReport(UNKNOWN)

    expect(inWindow('[data-test="report-judgement"]')?.textContent).toContain('No report yet')
    expect(inWindow('[data-test="report-summary"]')?.textContent.trim()).toBe(
      'VirusTotal has no report on it yet.',
    )
    expect(inWindow('[data-test="report-bar"]')).toBeNull()
    expect(inWindow('[data-test="report-counts"]')).toBeNull()
    expect(inWindow('[data-test="report-analysed"]')?.textContent).toBe('Never')
    expect(inWindow('[data-test="report-reputation"]')?.textContent).toBe('No score yet')
  })

  it('shows the community score with its sign', async () => {
    const { inWindow } = await mountReport({ ...MALICIOUS, reputation: 5 })

    expect(inWindow('[data-test="report-reputation"]')?.textContent).toBe('+5')
  })

  it('shows what else VirusTotal says, and the categories it was given', async () => {
    const { inWindow, all } = await mountReport()

    expect(inWindow('[data-test="report-analysed"]')?.textContent).toBeTruthy()
    expect(
      all('[data-test="report-categories"] .v-chip').map((chip) => chip.textContent.trim()),
    ).toEqual(['malware', 'phishing'])
    expect(document.querySelector('.v-overlay--active')?.textContent).toContain('Example Hosting')
  })

  it('opens the subject on VirusTotal in a new tab, without giving that page this one', async () => {
    const { inWindow } = await mountReport()

    const link = inWindow('[data-test="report-open"]') as HTMLAnchorElement
    expect(link.textContent.trim()).toBe('Open in VirusTotal')
    expect(link.getAttribute('href')).toBe(
      'https://www.virustotal.com/gui/ip-address/93.184.216.34',
    )
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('closes from its close button', async () => {
    const { inWindow, onUpdate } = await mountReport()
    const close = inWindow('[data-test="report-close"]') as HTMLElement

    close.click()

    expect(onUpdate).toHaveBeenLastCalledWith(false)
  })

  it('closes from Done', async () => {
    const { inWindow, onUpdate } = await mountReport()
    const done = inWindow('[data-test="report-done"]') as HTMLElement

    done.click()

    expect(onUpdate).toHaveBeenLastCalledWith(false)
  })

  it('fills the whole screen on a phone', async () => {
    const { inWindow } = await mountReport(MALICIOUS, { width: 400 })

    expect(inWindow('[data-test="threat-report"]')?.classList).toContain('report--screen')
  })
})
