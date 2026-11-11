import * as trustApi from '@/api/trust'
import TrustButton from '@/components/TrustButton.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { trustRule } from '@/test/trust'

async function button(props: Record<string, unknown> = {}) {
  const post = vi.spyOn(trustApi, 'trust').mockResolvedValue(trustRule({ id: 9 }))
  const mounted = await mountWithPlugins(TrustButton, {
    props: { address: '52.1.2.3', ...props },
    withApp: true,
    signedIn: 'admin',
  })
  const trigger = mounted.wrapper.find('[data-test="trust-button"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  return { ...mounted, post, trigger, inDialog }
}

describe('TrustButton', () => {
  it('says which address it trusts, for a screen reader', async () => {
    const { trigger } = await button()

    expect(trigger.text()).toBe('Trust')
    expect(trigger.attributes('aria-label')).toBe('Trust 52.1.2.3')
  })

  it('can be small, for a list', async () => {
    const { trigger } = await button({ small: true })

    expect(trigger.classes()).toContain('v-btn--size-small')
  })

  it('asks what to trust: the whole address, and the device and alert where they are known', async () => {
    const { trigger, inDialog } = await button({
      device: { address: '192.168.1.30', name: 'Blink camera' },
      signature: 'ET POLICY Odd call',
    })

    await trigger.trigger('click')
    await flushPromises()

    expect(inDialog('scope-traffic')).not.toBeNull()
    expect(inDialog('scope-alert')).not.toBeNull()
    expect(inDialog('scope-address')).not.toBeNull()
  })

  it('offers only the address when that is all it knows', async () => {
    const { trigger, inDialog } = await button()

    await trigger.trigger('click')
    await flushPromises()

    expect(inDialog('scope-address')).not.toBeNull()
    expect(inDialog('scope-traffic')).toBeNull()
  })

  it('says `trusted` with what was saved, for the page to read again', async () => {
    const { trigger, inDialog, wrapper } = await button()
    await trigger.trigger('click')
    await flushPromises()

    inDialog('trust-save')!.click()
    await flushPromises()
    await flushPromises()

    expect(wrapper.findComponent(TrustButton).emitted('trusted')).toEqual([[trustRule({ id: 9 })]])
  })
})
