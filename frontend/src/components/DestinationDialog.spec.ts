import { defineComponent, h, ref } from 'vue'

import type { Destination } from '@/api/alerts'
import DestinationDialog from '@/components/DestinationDialog.vue'
import { destination } from '@/test/alerts'
import { flushPromises, mountWithPlugins } from '@/test/mount'

interface Props {
  destination?: Destination | null
  busy?: boolean
  problems?: Record<string, string>
  failure?: string | null
}

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(props: Props = {}) {
  const saved = vi.fn<(answer: { name: string; url: string }) => void>()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Open'),
        h(DestinationDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          destination: null,
          ...props,
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
  const write = async (field: 'dialog-name' | 'dialog-url', text: string) => {
    const input = inDialog(field)!.querySelector('input')!
    input.value = text
    input.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const save = async () => {
    inDialog('dialog-save')!.click()
    await flushPromises()
  }
  return { ...mounted, saved, open, inDialog, openIt, write, save }
}

const ADDRESS = 'https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz'

describe('DestinationDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()

    expect(inDialog('destination-dialog')).toBeNull()
  })

  describe('adding one', () => {
    it('asks for a name and the webhook address, and explains where to get it', async () => {
      const { inDialog, openIt } = await mountDialog()

      await openIt()

      expect(inDialog('dialog-title')!.textContent).toBe('Add a Discord destination')
      expect(inDialog('dialog-url')!.textContent).toContain('Starts with https://discord.com/')
      expect(inDialog('dialog-help')!.textContent).toContain('copy its URL')
      expect(inDialog('dialog-help')!.querySelector('a')!.getAttribute('href')).toBe(
        'https://support.discord.com/hc/en-us/articles/360045093012',
      )
      expect(inDialog('dialog-save')!.textContent).toContain('Add destination')
    })

    it('cannot be saved until both are filled in', async () => {
      const { inDialog, openIt, write, saved, save } = await mountDialog()
      await openIt()
      expect(inDialog('dialog-save')!.hasAttribute('disabled')).toBe(true)

      await write('dialog-name', 'Security')
      expect(inDialog('dialog-save')!.hasAttribute('disabled')).toBe(true)
      await write('dialog-url', '   ')
      expect(inDialog('dialog-save')!.hasAttribute('disabled')).toBe(true)
      await write('dialog-url', ADDRESS)
      expect(inDialog('dialog-save')!.hasAttribute('disabled')).toBe(false)
      await save()

      expect(saved).toHaveBeenCalledWith({ name: 'Security', url: ADDRESS })
    })

    it('does not save with a name of only spaces', async () => {
      const { openIt, write, saved, wrapper } = await mountDialog()
      await openIt()
      await write('dialog-name', '   ')
      await write('dialog-url', ADDRESS)

      document
        .querySelector('[data-test="destination-dialog"] form')!
        .dispatchEvent(new Event('submit', { cancelable: true }))
      await flushPromises()

      expect(saved).not.toHaveBeenCalled()
      expect(wrapper.exists()).toBe(true)
    })

    it('trims what was typed', async () => {
      const { openIt, write, saved, save } = await mountDialog()
      await openIt()
      await write('dialog-name', '  Security  ')
      await write('dialog-url', `  ${ADDRESS}  `)

      await save()

      expect(saved).toHaveBeenCalledWith({ name: 'Security', url: ADDRESS })
    })

    it('does not show the address unless asked', async () => {
      const { inDialog, openIt, write } = await mountDialog()
      await openIt()
      await write('dialog-url', ADDRESS)

      const input = inDialog('dialog-url')!.querySelector('input')!
      expect(input.type).toBe('password')
      inDialog('dialog-url')!.querySelector<HTMLElement>('[data-test="show-secret"]')!.click()
      await flushPromises()
      expect(input.type).toBe('text')
    })
  })

  describe('changing one', () => {
    it('shows its name, keeps its address when that is left empty, and says so', async () => {
      const { inDialog, openIt, saved, save } = await mountDialog({ destination: destination() })

      await openIt()

      expect(inDialog('dialog-title')!.textContent).toBe('Change this destination')
      expect(inDialog('dialog-name')!.querySelector('input')!.value).toBe('Security channel')
      expect(inDialog('dialog-url')!.textContent).toContain('Saved. Leave this empty to keep it')
      expect(inDialog('dialog-save')!.textContent).toContain('Save')
      await save()
      expect(saved).toHaveBeenCalledWith({ name: 'Security channel', url: '' })
    })

    it('sends a new address to replace the old', async () => {
      const { openIt, write, saved, save } = await mountDialog({ destination: destination() })
      await openIt()
      await write('dialog-url', ADDRESS)

      await save()

      expect(saved).toHaveBeenCalledWith({ name: 'Security channel', url: ADDRESS })
    })

    it('shows what is kept now each time it opens, not what an earlier visit left', async () => {
      const { inDialog, openIt, write, open } = await mountDialog({ destination: destination() })
      await openIt()
      await write('dialog-name', 'Something else')
      open.value = false
      await flushPromises()

      await openIt()

      expect(inDialog('dialog-name')!.querySelector('input')!.value).toBe('Security channel')
    })
  })

  it('shows what was wrong with each field', async () => {
    const { inDialog, openIt } = await mountDialog({
      problems: {
        name: "There's already a destination called Security.",
        url: 'That is not a webhook.',
      },
    })

    await openIt()

    expect(inDialog('dialog-name')!.textContent).toContain("There's already a destination")
    expect(inDialog('dialog-url')!.textContent).toContain('That is not a webhook.')
  })

  it('shows a failure that is not about a field', async () => {
    const { inDialog, openIt } = await mountDialog({ failure: "Can't reach AresGate." })

    await openIt()

    expect(inDialog('dialog-failure')!.textContent).toContain("Can't reach AresGate.")
  })

  it('closes when cancelled', async () => {
    const { inDialog, openIt, open } = await mountDialog()
    await openIt()

    inDialog('dialog-cancel')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
  })

  it('cannot be cancelled while it is saving', async () => {
    const { inDialog, openIt } = await mountDialog({ busy: true })

    await openIt()

    expect((inDialog('dialog-cancel') as HTMLButtonElement).disabled).toBe(true)
  })

  it('gives the keyboard back to what opened it', async () => {
    const { inDialog, openIt, wrapper, open } = await mountDialog()
    await openIt()
    inDialog('dialog-cancel')!.click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 400))

    expect(open.value).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('[data-test="opener"]').element)
  })
})
