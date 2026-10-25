import { defineComponent, h, ref } from 'vue'

import RetentionDialog from '@/components/RetentionDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(props: Record<string, unknown> = {}) {
  const saved = vi.fn()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Change'),
        h(RetentionDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          title: "How long to keep OPNsense's events",
          noun: 'events',
          defaultDays: 30,
          days: null,
          onSave: saved,
          ...props,
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  const opener = mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const input = (selector: string) =>
    document.querySelector<HTMLInputElement>(`[data-test="${selector}"] input`)
  const openIt = async () => {
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
  }
  const type = async (days: string) => {
    const field = input('retention-days')!
    field.value = days
    field.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const submit = async () => {
    inDialog('retention-save')!.click()
    await flushPromises()
    await flushPromises()
  }
  const choose = async (selector: string) => {
    input(selector)!.click()
    await flushPromises()
  }
  return { ...mounted, saved, open, opener, inDialog, input, openIt, type, submit, choose }
}

describe('RetentionDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()
    expect(inDialog('retention-dialog')).toBeNull()
  })

  it('asks how long, naming whose data it is and what the default is', async () => {
    const { inDialog, openIt } = await mountDialog()

    await openIt()

    expect(inDialog('retention-title')?.textContent).toBe("How long to keep OPNsense's events")
    expect(inDialog('retention-default')?.textContent).toContain('Use the default, 30 days')
    expect(inDialog('retention-custom')?.textContent).toContain('Choose a number of days')
    expect(inDialog('retention-dialog')?.textContent).toContain(
      'A longer time keeps more events to look back through',
    )
  })

  it('is named by its title, for people who cannot see it', async () => {
    const { inDialog, openIt } = await mountDialog()
    await openIt()
    const dialog = document.querySelector('[role="dialog"]')
    const title = inDialog('retention-title')!
    expect(dialog?.getAttribute('aria-labelledby')).toBe(title.id)
  })

  it('starts on the default when the integration has no time of its own', async () => {
    const { input, openIt } = await mountDialog()

    await openIt()

    expect(input('retention-default')?.checked).toBe(true)
    expect(input('retention-custom')?.checked).toBe(false)
    expect(input('retention-days')?.disabled).toBe(true)
    expect(input('retention-days')?.value).toBe('30')
  })

  it('starts on the days it has been given, and shows them', async () => {
    const { input, openIt } = await mountDialog({ days: 90 })

    await openIt()

    expect(input('retention-custom')?.checked).toBe(true)
    expect(input('retention-days')?.disabled).toBe(false)
    expect(input('retention-days')?.value).toBe('90')
  })

  it('saves the default as null', async () => {
    const { openIt, submit, saved } = await mountDialog({ days: 90 })
    await openIt()
    const defaultChoice = document.querySelector<HTMLInputElement>(
      '[data-test="retention-default"] input',
    )!
    defaultChoice.click()
    await flushPromises()

    await submit()

    expect(saved).toHaveBeenCalledExactlyOnceWith(null)
  })

  it('saves the days that were typed, as a number', async () => {
    const { openIt, choose, type, submit, saved } = await mountDialog()
    await openIt()
    await choose('retention-custom')

    await type('7')
    await submit()

    expect(saved).toHaveBeenCalledExactlyOnceWith(7)
  })

  it.each(['', '0', '-3', '1.5', '3651', 'abc', '1e2'])(
    'refuses %j, saying what is allowed, and moves the keyboard to the field',
    async (typed) => {
      const { openIt, choose, type, submit, saved, inDialog, input } = await mountDialog()
      await openIt()
      await choose('retention-custom')

      await type(typed)
      await submit()

      expect(saved).not.toHaveBeenCalled()
      expect(inDialog('retention-dialog')?.textContent).toContain(
        'Enter a whole number of days from 1 to 3650.',
      )
      expect(document.activeElement).toBe(input('retention-days'))
    },
  )

  it.each(['1', '45', '3650'])('takes %j', async (typed) => {
    const { openIt, choose, type, submit, saved } = await mountDialog()
    await openIt()
    await choose('retention-custom')

    await type(typed)
    await submit()

    expect(saved).toHaveBeenCalledExactlyOnceWith(Number(typed))
  })

  it('does not check the days while the default is chosen', async () => {
    const { openIt, type, submit, saved } = await mountDialog({ days: 90 })
    await openIt()
    await type('nonsense')
    document.querySelector<HTMLInputElement>('[data-test="retention-default"] input')!.click()
    await flushPromises()

    await submit()

    expect(saved).toHaveBeenCalledExactlyOnceWith(null)
  })

  it('closes without saving on Cancel', async () => {
    const { openIt, inDialog, saved, open } = await mountDialog()
    await openIt()

    inDialog('retention-cancel')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
    expect(saved).not.toHaveBeenCalled()
  })

  it('closes on Escape, as dialogs do', async () => {
    const { openIt, inDialog, open, saved } = await mountDialog()
    await openIt()

    inDialog('retention-dialog')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()

    expect(open.value).toBe(false)
    expect(saved).not.toHaveBeenCalled()
  })

  it('forgets what was typed the last time and shows what is set now', async () => {
    const { openIt, choose, type, input, inDialog, open, wrapper } = await mountDialog({
      days: 14,
    })
    await openIt()
    await type('99')
    inDialog('retention-cancel')!.click()
    await flushPromises()
    expect(open.value).toBe(false)

    await openIt()
    await flushPromises()
    await choose('retention-custom')

    expect(input('retention-days')?.value).toBe('14')
    expect(wrapper.exists()).toBe(true)
  })

  it('cannot be closed or sent again while it is saving', async () => {
    const { openIt, inDialog } = await mountDialog({ busy: true })
    await openIt()

    expect((inDialog('retention-cancel') as HTMLButtonElement | null)?.disabled).toBe(true)
    expect(inDialog('retention-save')?.className).toContain('v-btn--loading')
    // Pressing Escape doesn't close it either.
    inDialog('retention-dialog')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()
    expect(inDialog('retention-dialog')).not.toBeNull()
  })

  it('gives the keyboard back to what opened it', async () => {
    const { openIt, inDialog, opener } = await mountDialog()
    await openIt()

    inDialog('retention-cancel')!.click()
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(opener.element)
    })
  })
})
