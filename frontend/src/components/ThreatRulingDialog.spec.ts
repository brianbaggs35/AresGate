import ThreatRulingDialog from '@/components/ThreatRulingDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { SAFE_RULING } from '@/test/threatIntel'

async function mountDialog(
  props: Record<string, unknown> = {},
  { width, onUpdate = vi.fn() }: { width?: number; onUpdate?: (open: boolean) => void } = {},
) {
  const mounted = await mountWithPlugins(ThreatRulingDialog, {
    withApp: true,
    signedIn: 'brian',
    width,
    props: {
      subject: '93.184.216.34',
      ruling: null,
      modelValue: true,
      'onUpdate:modelValue': onUpdate,
      ...props,
    },
  })
  await flushPromises()
  const inWindow = (selector: string) =>
    document.querySelector<HTMLElement>(`.v-overlay--active ${selector}`)
  return { ...mounted, inWindow, onUpdate }
}

describe('ThreatRulingDialog', () => {
  it('names what is ruled on and has the owner rule on it', async () => {
    const { inWindow } = await mountDialog()

    expect(inWindow('[data-test="ruling-subject"]')?.textContent.trim()).toBe('93.184.216.34')
    expect(inWindow('[data-test="ruling"]')).not.toBeNull()
    expect(inWindow('[data-test="ruling-heard"]')).toBeNull()
  })

  it('says what the services said of it, where they said anything', async () => {
    const { inWindow } = await mountDialog({ heard: 'VirusTotal said: no engine of 90 flags it.' })

    expect(inWindow('[data-test="ruling-heard"]')?.textContent.trim()).toBe(
      'VirusTotal said: no engine of 90 flags it.',
    )
  })

  it('starts from what was ruled already', async () => {
    const { inWindow } = await mountDialog({ ruling: SAFE_RULING })

    expect(inWindow('[data-test="ruling-choice-safe"] input')?.matches(':checked')).toBe(true)
  })

  it('says what was ruled to the page that opened it', async () => {
    const onChanged = vi.fn()
    const { wrapper } = await mountDialog({ onChanged })

    wrapper.findComponent({ name: 'ThreatRuling' }).vm.$emit('changed', SAFE_RULING)

    expect(onChanged).toHaveBeenCalledWith(SAFE_RULING)
  })

  it('closes from its close button and from Done', async () => {
    const onUpdate = vi.fn()
    const { inWindow } = await mountDialog({}, { onUpdate })

    inWindow('[data-test="ruling-close"]')?.click()
    inWindow('[data-test="ruling-done"]')?.click()

    expect(onUpdate).toHaveBeenCalledTimes(2)
    expect(onUpdate).toHaveBeenCalledWith(false)
  })

  it('fills the whole screen on a phone', async () => {
    const { inWindow } = await mountDialog({}, { width: 400 })

    expect(inWindow('[data-test="ruling-dialog"]')?.classList).toContain('dialog--screen')
  })
})
