import { VDialog } from 'vuetify/components'

import ThreatCveDialog from '@/components/ThreatCveDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { EXPLOITED_CVE, MEDIUM_CVE, UNKNOWN_CVE } from '@/test/threatCatalog'

const NOTICE =
  'This product uses data from the NVD API but is not endorsed or certified by the NVD.'

async function mountDialog(
  cve = EXPLOITED_CVE,
  { width, onUpdate = vi.fn() }: { width?: number; onUpdate?: (open: boolean) => void } = {},
) {
  const mounted = await mountWithPlugins(ThreatCveDialog, {
    withApp: true,
    signedIn: 'brian',
    width,
    props: { cve, notice: NOTICE, modelValue: true, 'onUpdate:modelValue': onUpdate },
  })
  await flushPromises()
  const inWindow = (selector: string) =>
    document.querySelector<HTMLElement>(`.v-overlay--active ${selector}`)
  const text = (selector: string) => inWindow(selector)?.textContent.replace(/\s+/g, ' ').trim()
  return { ...mounted, inWindow, text, onUpdate }
}

describe('ThreatCveDialog', () => {
  it('shows how severe a CVE is, its score and what it is', async () => {
    const { inWindow, text } = await mountDialog()

    expect(text('.v-card h2')).toBe('CVE-2024-3400')
    expect(inWindow('[data-test="severity"]')?.textContent.trim()).toBe('Critical')
    expect(text('[data-test="cve-score"]')).toBe('10.0 CVSS 3.1')
    expect(text('[data-test="cve-description"]')).toContain('command injection')
  })

  it('says CISA lists it as exploited, what it asks to be done and by when', async () => {
    const { inWindow, text } = await mountDialog()

    expect(inWindow('[data-test="cve-exploited"]')).not.toBeNull()
    expect(text('[data-test="cve-kev"]')).toContain(
      'Palo Alto Networks PAN-OS Command Injection Vulnerability',
    )
    expect(text('[data-test="cve-kev"]')).toContain('Known Exploited Vulnerabilities catalog since')
    expect(text('[data-test="cve-action"]')).toContain('Apply the mitigations the vendor lists.')
    expect(text('[data-test="cve-action"]')).toContain('Due')
  })

  it('tells the weaknesses behind it, its status, its dates and its vector', async () => {
    const { text } = await mountDialog()

    expect(text('[data-test="cve-weaknesses"]')).toContain('CWE-77')
    expect(text('[data-test="cve-weaknesses"]')).toContain('CWE-20')
    const facts = text('[data-test="cve-facts"]')
    expect(facts).toContain('Analyzed')
    expect(facts).toContain('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H')
    expect(facts).toContain('Published')
    expect(facts).toContain('Last changed')
  })

  it('leaves out what NVD did not say, and what is not exploited', async () => {
    const { inWindow, text } = await mountDialog(MEDIUM_CVE)

    expect(text('[data-test="cve-score"]')).toBe('5.4 CVSS 3.1')
    expect(inWindow('[data-test="cve-description"]')).toBeNull()
    expect(inWindow('[data-test="cve-exploited"]')).toBeNull()
    expect(inWindow('[data-test="cve-kev"]')).toBeNull()
    expect(inWindow('[data-test="cve-weaknesses"]')).toBeNull()
    expect(text('[data-test="cve-facts"]')).not.toContain('Vector')
  })

  it('says only what CISA says where it gives neither a date nor an action', async () => {
    const { text } = await mountDialog({
      ...EXPLOITED_CVE,
      kev_name: null,
      exploited_on: null,
      required_action: null,
      action_due: null,
    })

    expect(text('[data-test="cve-kev"]')).toBe(
      'CISA lists it in its Known Exploited Vulnerabilities catalog, which means someone has been seen using it against real systems.',
    )
  })

  it('gives no due date for an action without one', async () => {
    const { text } = await mountDialog({ ...EXPLOITED_CVE, action_due: null })

    expect(text('[data-test="cve-action"]')).not.toContain('Due')
  })

  it('leaves out the dates NVD did not give', async () => {
    const { text } = await mountDialog({ ...MEDIUM_CVE, published_at: null, modified_at: null })

    expect(text('[data-test="cve-facts"]')).toContain('Analyzed')
    expect(text('[data-test="cve-facts"]')).not.toContain('Published')
    expect(text('[data-test="cve-facts"]')).not.toContain('Last changed')
  })

  it('says a CVE is not scored yet while NVD gives it no score', async () => {
    const { inWindow } = await mountDialog({
      ...MEDIUM_CVE,
      score: null,
      rating: 'unrated',
      cvss_version: null,
    })

    expect(inWindow('[data-test="cve-unrated"]')?.textContent.trim()).toBe('Not scored yet')
    expect(inWindow('[data-test="cve-score"]')).toBeNull()
    expect(inWindow('[data-test="severity"]')).toBeNull()
  })

  it('says NVD has no record of a CVE it does not know', async () => {
    const { inWindow, text } = await mountDialog(UNKNOWN_CVE)

    expect(text('[data-test="cve-unknown"]')).toContain('NVD has no record of this CVE yet')
    expect(inWindow('[data-test="cve-score"]')).toBeNull()
    expect(inWindow('[data-test="cve-facts"]')).toBeNull()
  })

  it('says when NVD was asked, carries the notice NVD asks for and links to its page', async () => {
    const { inWindow, text } = await mountDialog()

    expect(text('[data-test="cve-checked"]')).toMatch(/^AresGate asked NVD /)
    expect(text('[data-test="cve-notice"]')).toBe(NOTICE)
    const link = inWindow('[data-test="cve-link"]')
    expect(link?.getAttribute('href')).toBe('https://nvd.nist.gov/vuln/detail/CVE-2024-3400')
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('closes from its close button and from Done', async () => {
    const onUpdate = vi.fn()
    const { inWindow } = await mountDialog(EXPLOITED_CVE, { onUpdate })

    inWindow('[data-test="cve-close"]')?.click()
    inWindow('[data-test="cve-done"]')?.click()

    expect(onUpdate).toHaveBeenCalledTimes(2)
    expect(onUpdate).toHaveBeenCalledWith(false)
  })

  it('fills the whole screen on a phone', async () => {
    const { inWindow } = await mountDialog(EXPLOITED_CVE, { width: 400 })

    expect(inWindow('[data-test="cve-dialog"]')?.classList).toContain('dialog--screen')
  })

  it('moves the keyboard to what it is about once it has opened', async () => {
    const { wrapper, inWindow } = await mountDialog()

    wrapper.findComponent(VDialog).vm.$emit('afterEnter')

    expect(document.activeElement).toBe(inWindow('.v-card h2'))
  })

  it('says so when the window asks to be closed', async () => {
    const onUpdate = vi.fn()
    const { wrapper } = await mountDialog(EXPLOITED_CVE, { onUpdate })

    wrapper.findComponent(VDialog).vm.$emit('update:modelValue', false)

    expect(onUpdate).toHaveBeenCalledWith(false)
  })
})
