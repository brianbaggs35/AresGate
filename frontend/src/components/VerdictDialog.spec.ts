import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import type { Verdict, VerdictChange } from '@/api/verdicts'
import VerdictDialog from '@/components/VerdictDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { verdict } from '@/test/verdicts'

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(rule: Verdict | null = verdict({ note: 'my scanner' }), busy = false) {
  const saved = vi.fn<(change: VerdictChange) => void>()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Change'),
        h(VerdictDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          rule,
          busy,
          onSave: saved,
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const openIt = async () => {
    mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]').element.focus()
    await mounted.wrapper.find('[data-test="opener"]').trigger('click')
    await flushPromises()
  }
  const say = async (kind: string) => {
    inDialog(`say-${kind}`)!.querySelector('input')!.click()
    await flushPromises()
  }
  const write = async (text: string) => {
    const field = inDialog('dialog-note')!.querySelector('input')!
    field.value = text
    field.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const save = async () => {
    inDialog('dialog-save')!.click()
    await flushPromises()
  }
  return { ...mounted, saved, open, inDialog, openIt, say, write, save }
}

describe('VerdictDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()

    expect(inDialog('verdict-dialog')).toBeNull()
  })

  it('names the verdict and what it says now', async () => {
    const { inDialog, openIt } = await mountDialog()

    await openIt()

    expect(inDialog('dialog-about')?.textContent.trim()).toBe('93.184.216.34')
    expect(inDialog('say-not_suspicious')!.querySelector('input')!.checked).toBe(true)
    expect(inDialog('dialog-note')!.querySelector('input')!.value).toBe('my scanner')
  })

  it('explains each thing that can be said', async () => {
    const { inDialog, openIt } = await mountDialog()

    await openIt()

    expect(inDialog('say-threat')?.textContent).toContain('AresGate is certain of it')
    expect(inDialog('say-low_priority')?.textContent).toContain('Low priority')
  })

  it('saves what was chosen and written, with the note trimmed', async () => {
    const { openIt, say, write, save, saved } = await mountDialog()
    await openIt()

    await say('threat')
    await write('  it came back  ')
    await save()

    expect(saved).toHaveBeenCalledWith({ verdict: 'threat', note: 'it came back' })
  })

  it('takes the note off when it is emptied', async () => {
    const { openIt, write, save, saved } = await mountDialog()
    await openIt()

    await write('   ')
    await save()

    expect(saved).toHaveBeenCalledWith({ verdict: 'not_suspicious', note: null })
  })

  it('shows what the verdict says each time, not what an earlier visit left', async () => {
    const { openIt, say, write, open, inDialog } = await mountDialog()
    await openIt()
    await say('threat')
    await write('changed my mind')
    open.value = false
    await flushPromises()

    await openIt()

    expect(inDialog('say-not_suspicious')!.querySelector('input')!.checked).toBe(true)
    expect(inDialog('dialog-note')!.querySelector('input')!.value).toBe('my scanner')
  })

  it('shows an empty note for a verdict that has none', async () => {
    const { openIt, inDialog } = await mountDialog(verdict({ note: null, verdict: 'threat' }))

    await openIt()

    expect(inDialog('dialog-note')!.querySelector('input')!.value).toBe('')
    expect(inDialog('say-threat')!.querySelector('input')!.checked).toBe(true)
  })

  it('closes without saving when cancelled', async () => {
    const { openIt, inDialog, saved, open } = await mountDialog()
    await openIt()

    inDialog('dialog-cancel')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
    expect(saved).not.toHaveBeenCalled()
  })

  it('closes without saving when the dialog is dismissed, as Escape does', async () => {
    const { wrapper, openIt, saved, open } = await mountDialog()
    await openIt()

    wrapper.findComponent(VDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(open.value).toBe(false)
    expect(saved).not.toHaveBeenCalled()
  })

  it('gives the keyboard back to what opened it, once it has gone', async () => {
    const { wrapper, openIt, inDialog } = await mountDialog()
    await openIt()
    inDialog('dialog-cancel')!.focus()

    // jsdom plays no transitions, so the end of the one that closes the dialog is announced here.
    wrapper.findComponent(VDialog).vm.$emit('afterLeave')

    expect(document.activeElement).toBe(wrapper.find('[data-test="opener"]').element)
  })

  it('cannot be left while it saves', async () => {
    const { openIt, inDialog } = await mountDialog(verdict(), true)
    await openIt()

    expect((inDialog('dialog-cancel') as HTMLButtonElement).disabled).toBe(true)
  })

  it('has nothing to show before a verdict is chosen', async () => {
    const { openIt, inDialog } = await mountDialog(null)

    await openIt()

    expect(inDialog('dialog-about')).toBeNull()
    expect(inDialog('dialog-note')!.querySelector('input')!.value).toBe('')
  })
})
