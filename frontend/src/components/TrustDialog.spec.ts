import { defineComponent, h, ref } from 'vue'

import { ApiError } from '@/api/client'
import * as trustApi from '@/api/trust'
import type { Trust } from '@/api/trust'
import TrustDialog from '@/components/TrustDialog.vue'
import { scopesFor, type Scope } from '@/trust'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { trustRule } from '@/test/trust'

const SCOPES = scopesFor({
  address: '52.1.2.3',
  device: { address: '192.168.1.30', name: 'Blink camera' },
  signature: 'ET POLICY Odd call',
})

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(scopes: Scope[] = SCOPES) {
  const trusted = vi.fn<(rule: Trust) => void>()
  const post = vi.spyOn(trustApi, 'trust').mockResolvedValue(trustRule({ id: 9 }))
  const open = ref(false)
  const choices = ref(scopes)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Open'),
        h(TrustDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          scopes: choices.value,
          onTrusted: trusted,
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true, signedIn: 'admin' })
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    inDialog(selector)!.click()
    await flushPromises()
  }
  const radio = async (selector: string) => {
    inDialog(selector)!.querySelector('input')!.click()
    await flushPromises()
  }
  const type = async (selector: string, text: string) => {
    const field = inDialog(selector)!.querySelector('input')!
    field.value = text
    field.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const openIt = async () => {
    await mounted.wrapper.find('[data-test="opener"]').trigger('click')
    await flushPromises()
  }
  return { ...mounted, trusted, post, open, choices, inDialog, click, radio, type, openIt }
}

describe('TrustDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()

    expect(inDialog('trust-dialog')).toBeNull()
  })

  describe('with choices of what to trust', () => {
    it('offers each, the narrowest chosen and safe, and says it is for every program', async () => {
      const { inDialog, openIt } = await mountDialog()
      await openIt()

      expect(inDialog('trust-dialog')?.textContent).toContain('whichever program reports it')
      expect(inDialog('scope-traffic')?.textContent).toContain('Only what Blink camera sends')
      expect(inDialog('scope-alert')).not.toBeNull()
      expect(inDialog('scope-address')).not.toBeNull()
      expect(inDialog('scope-traffic')!.querySelector('input')!.checked).toBe(true)
      expect(inDialog('level-not_suspicious')!.querySelector('input')!.checked).toBe(true)
    })

    it('trusts the narrowest, as safe, and says what it saved', async () => {
      const { post, trusted, open, click, openIt } = await mountDialog()
      await openIt()

      await click('trust-save')
      await flushPromises()

      expect(post).toHaveBeenCalledWith(
        {
          address: '192.168.1.30',
          destination: '52.1.2.3',
          verdict: 'not_suspicious',
          note: '',
        },
        'a-security-token',
      )
      expect(trusted).toHaveBeenCalledWith(trustRule({ id: 9 }))
      expect(open.value).toBe(false)
    })

    it('trusts what was chosen, how much, and why', async () => {
      const { post, radio, type, click, openIt } = await mountDialog()
      await openIt()

      await radio('scope-address')
      await radio('level-low_priority')
      await type('field-note', '  my camera ')
      await click('trust-save')
      await flushPromises()

      expect(post).toHaveBeenCalledWith(
        { address: '52.1.2.3', verdict: 'low_priority', note: 'my camera' },
        'a-security-token',
      )
    })

    it('starts again from the narrowest, and safe, each time it opens', async () => {
      const { radio, type, click, inDialog, open, openIt } = await mountDialog()
      await openIt()
      await radio('scope-address')
      await radio('level-low_priority')
      await type('field-note', 'something')
      await click('trust-cancel')
      expect(open.value).toBe(false)

      await openIt()

      expect(inDialog('scope-traffic')!.querySelector('input')!.checked).toBe(true)
      expect(inDialog('level-not_suspicious')!.querySelector('input')!.checked).toBe(true)
      expect(inDialog('field-note')!.querySelector('input')!.value).toBe('')
    })

    it('says why it could not be saved, and stays open', async () => {
      const { post, trusted, open, click, inDialog, openIt } = await mountDialog()
      post.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await openIt()

      await click('trust-save')
      await flushPromises()

      expect(inDialog('trust-failure')?.textContent).toContain("Can't reach AresGate.")
      expect(trusted).not.toHaveBeenCalled()
      expect(open.value).toBe(true)
    })

    it('forgets the failure when it is opened again', async () => {
      const { post, click, inDialog, openIt } = await mountDialog()
      post.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await openIt()
      await click('trust-save')
      await flushPromises()
      await click('trust-cancel')

      await openIt()

      expect(inDialog('trust-failure')).toBeNull()
    })

    it('closes when it is dismissed, as by Escape', async () => {
      const { open, openIt } = await mountDialog()
      await openIt()

      document
        .querySelector('.v-overlay')!
        .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      await flushPromises()

      expect(open.value).toBe(false)
    })

    it('saves nothing when the choices changed under it and the one chosen is gone', async () => {
      const { post, choices, click, openIt } = await mountDialog()
      await openIt()

      choices.value = scopesFor({ address: '8.8.8.8' })
        .slice(0, 1)
        .map((scope) => ({
          ...scope,
          key: 'other',
        }))
      await flushPromises()
      await click('trust-save')

      expect(post).not.toHaveBeenCalled()
    })
  })

  describe('with no choices, as the whole form', () => {
    it('asks for something to be named', async () => {
      const { inDialog, click, post, openIt } = await mountDialog([])
      await openIt()

      expect(inDialog('trust-form')).not.toBeNull()
      await click('trust-save')

      expect(inDialog('trust-problem')?.textContent).toContain('Say what to trust')
      expect(post).not.toHaveBeenCalled()
    })

    it('trusts what was typed', async () => {
      const { inDialog, type, click, post, trusted, openIt } = await mountDialog([])
      await openIt()

      await type('field-address', '52.1.2.3')
      await click('trust-save')
      await flushPromises()

      expect(post).toHaveBeenCalledWith(
        { verdict: 'not_suspicious', note: '', address: '52.1.2.3' },
        'a-security-token',
      )
      expect(trusted).toHaveBeenCalled()
      expect(inDialog('trust-form')).not.toBeNull()
    })

    it('closes when it is cancelled', async () => {
      const { click, open, openIt } = await mountDialog([])
      await openIt()

      await click('trust-cancel')

      expect(open.value).toBe(false)
    })
  })
})
