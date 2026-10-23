import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(props: Record<string, unknown> = {}) {
  const confirmed = vi.fn()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Remove'),
        h(
          ConfirmDialog,
          {
            modelValue: open.value,
            'onUpdate:modelValue': (value: boolean) => (open.value = value),
            title: 'Remove it?',
            confirmLabel: 'Remove',
            onConfirm: confirmed,
            ...props,
          },
          () => 'It goes away.',
        ),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  const opener = mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]')
  const inDialog = (selector: string) => document.querySelector<HTMLButtonElement>(selector)
  const openIt = async () => {
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
  }
  return { ...mounted, confirmed, open, opener, inDialog, openIt }
}

describe('ConfirmDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()
    expect(inDialog('[data-test="confirm-dialog"]')).toBeNull()
  })

  it('asks, naming the action and saying what will happen', async () => {
    const { inDialog, openIt, confirmed } = await mountDialog()

    await openIt()

    expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe('Remove it?')
    expect(inDialog('[data-test="confirm-message"]')?.textContent).toBe('It goes away.')
    expect(inDialog('[data-test="confirm-accept"]')?.textContent.trim()).toBe('Remove')
    expect(inDialog('[data-test="confirm-cancel"]')?.textContent.trim()).toBe('Cancel')
    expect(confirmed).not.toHaveBeenCalled()
  })

  it('is named by its title, for people who cannot see it', async () => {
    const { inDialog, openIt } = await mountDialog()
    await openIt()
    const title = inDialog('[data-test="confirm-title"]')!
    expect(inDialog('[role="dialog"]')?.getAttribute('aria-labelledby')).toBe(title.id)
  })

  it('goes ahead when it is confirmed, and leaves closing to whoever asked', async () => {
    const { inDialog, openIt, confirmed, open } = await mountDialog()
    await openIt()

    inDialog('[data-test="confirm-accept"]')!.click()
    await flushPromises()

    expect(confirmed).toHaveBeenCalledOnce()
    expect(open.value).toBe(true)
  })

  it('closes when it is cancelled', async () => {
    const { inDialog, openIt, confirmed, open } = await mountDialog()
    await openIt()

    inDialog('[data-test="confirm-cancel"]')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
    expect(confirmed).not.toHaveBeenCalled()
  })

  it('gives the keyboard back to what opened it, once it has gone', async () => {
    const { wrapper, inDialog, openIt, opener } = await mountDialog()
    await openIt()
    inDialog('[data-test="confirm-cancel"]')!.focus()
    const dialog = wrapper.findComponent(VDialog)

    // jsdom plays no transitions, so the end of the one that closes the dialog is announced here.
    dialog.vm.$emit('afterLeave')

    expect(document.activeElement).toBe(opener.element)
    // And only once: it was forgotten, so a second announcement moves nothing.
    inDialog('[data-test="confirm-cancel"]')!.focus()
    dialog.vm.$emit('afterLeave')
    expect(document.activeElement).toBe(inDialog('[data-test="confirm-cancel"]'))
  })

  it('colors the button red for what removes something', async () => {
    const calm = await mountDialog()
    await calm.openIt()
    expect(calm.inDialog('[data-test="confirm-accept"]')?.className).toContain('bg-primary')
  })

  it('is red for what removes something', async () => {
    const { inDialog, openIt } = await mountDialog({ destructive: true })
    await openIt()
    expect(inDialog('[data-test="confirm-accept"]')?.className).toContain('bg-error')
  })

  it('closes on Escape, as dialogs do', async () => {
    const { inDialog, openIt, open } = await mountDialog()
    await openIt()

    inDialog('[data-test="confirm-dialog"]')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()

    expect(open.value).toBe(false)
  })

  it('cannot be left while the action is under way', async () => {
    const { inDialog, openIt, open } = await mountDialog({ busy: true })
    await openIt()

    expect(inDialog('[data-test="confirm-cancel"]')?.hasAttribute('disabled')).toBe(true)
    expect(inDialog('[data-test="confirm-accept"]')?.className).toContain('v-btn--loading')
    // Pressing Escape or clicking outside doesn't close it either.
    inDialog('[data-test="confirm-dialog"]')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()
    expect(open.value).toBe(true)
  })
})
