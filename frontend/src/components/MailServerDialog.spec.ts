import { defineComponent, h, ref } from 'vue'
import { VSelect } from 'vuetify/components'

import type { MailServer, MailServerChange, Security } from '@/api/alerts'
import MailServerDialog from '@/components/MailServerDialog.vue'
import { mailServer, noMailServer } from '@/test/alerts'
import { flushPromises, mountWithPlugins } from '@/test/mount'

interface Props {
  server?: MailServer
  busy?: boolean
  problems?: Record<string, string>
  failure?: string | null
}

/** The dialog in a page with a button that opens it, as pages use it. */
async function mountDialog(props: Props = {}) {
  const saved = vi.fn<(answer: MailServerChange) => void>()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Open'),
        h(MailServerDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          server: noMailServer(),
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
  const write = async (field: string, text: string) => {
    const input = inDialog(field)!.querySelector('input')!
    input.value = text
    input.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const save = async () => {
    inDialog('mail-save')!.click()
    await flushPromises()
  }
  const choose = async (value: Security) => {
    mounted.wrapper.findComponent(VSelect).vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  return { ...mounted, saved, open, inDialog, openIt, write, save, choose }
}

describe('MailServerDialog', () => {
  it('is closed until it is opened', async () => {
    const { inDialog } = await mountDialog()

    expect(inDialog('mail-dialog')).toBeNull()
  })

  describe('setting it up', () => {
    it('starts with the usual way to connect and cannot be saved until it has a server and a sender', async () => {
      const { inDialog, openIt, write, saved, save } = await mountDialog()

      await openIt()

      expect(inDialog('mail-dialog-title')!.textContent).toBe('Set up the mail server')
      expect(inDialog('mail-port')!.querySelector('input')!.value).toBe('587')
      expect(inDialog('mail-forget')).toBeNull()
      expect(inDialog('mail-save')!.hasAttribute('disabled')).toBe(true)
      await write('mail-host', 'smtp.example.com')
      expect(inDialog('mail-save')!.hasAttribute('disabled')).toBe(true)
      await write('mail-sender', '  alerts@example.com ')
      expect(inDialog('mail-save')!.hasAttribute('disabled')).toBe(false)
      await save()

      expect(saved).toHaveBeenCalledWith({
        host: 'smtp.example.com',
        port: 587,
        security: 'starttls',
        username: null,
        sender: 'alerts@example.com',
      })
    })

    it('sends the user name and the password, trimmed and as typed', async () => {
      const { openIt, write, saved, save } = await mountDialog()
      await openIt()
      await write('mail-host', ' smtp.example.com ')
      await write('mail-username', ' alerts@example.com ')
      await write('mail-password', ' a password ')
      await write('mail-sender', 'alerts@example.com')

      await save()

      expect(saved).toHaveBeenCalledWith({
        host: 'smtp.example.com',
        port: 587,
        security: 'starttls',
        username: 'alerts@example.com',
        sender: 'alerts@example.com',
        password: ' a password ',
      })
    })

    it.each(['', 'abc', '0', '65536', '123456', '5 87'])(
      'does not accept %j as a port',
      async (port) => {
        const { inDialog, openIt, write } = await mountDialog()
        await openIt()
        await write('mail-host', 'smtp.example.com')
        await write('mail-sender', 'alerts@example.com')

        await write('mail-port', port)

        expect(inDialog('mail-save')!.hasAttribute('disabled')).toBe(true)
      },
    )

    it('does not save when submitted before it is ready', async () => {
      const { openIt, saved } = await mountDialog()
      await openIt()

      document
        .querySelector('[data-test="mail-dialog"] form')!
        .dispatchEvent(new Event('submit', { cancelable: true }))
      await flushPromises()

      expect(saved).not.toHaveBeenCalled()
    })

    it('moves the port to the usual one for the way it connects, until the port was set by hand', async () => {
      const { inDialog, openIt, write, choose } = await mountDialog()
      await openIt()
      const port = () => inDialog('mail-port')!.querySelector('input')!.value

      await choose('ssl')
      expect(port()).toBe('465')
      await choose('none')
      expect(port()).toBe('25')
      await write('mail-port', '2525')
      await choose('starttls')
      expect(port()).toBe('2525')
    })

    it('sends the way it connects', async () => {
      const { openIt, write, choose, saved, save } = await mountDialog()
      await openIt()
      await write('mail-host', 'smtp.example.com')
      await write('mail-sender', 'alerts@example.com')
      await choose('ssl')

      await save()

      expect(saved).toHaveBeenCalledWith(expect.objectContaining({ port: 465, security: 'ssl' }))
    })
  })

  describe('changing it', () => {
    it('shows what is kept, keeps the password when it is left empty, and says so', async () => {
      const { inDialog, openIt, saved, save } = await mountDialog({ server: mailServer() })

      await openIt()

      expect(inDialog('mail-dialog-title')!.textContent).toBe('Change the mail server')
      expect(inDialog('mail-host')!.querySelector('input')!.value).toBe('smtp.example.com')
      expect(inDialog('mail-username')!.querySelector('input')!.value).toBe('alerts@example.com')
      expect(inDialog('mail-sender')!.querySelector('input')!.value).toBe('alerts@example.com')
      expect(inDialog('mail-password')!.textContent).toContain('Saved. Leave this empty to keep it')
      await save()
      expect(saved).toHaveBeenCalledWith({
        host: 'smtp.example.com',
        port: 587,
        security: 'starttls',
        username: 'alerts@example.com',
        sender: 'alerts@example.com',
      })
    })

    it('sends a new password to replace the old', async () => {
      const { openIt, write, saved, save } = await mountDialog({ server: mailServer() })
      await openIt()
      await write('mail-password', 'another')

      await save()

      expect(saved).toHaveBeenCalledWith(expect.objectContaining({ password: 'another' }))
    })

    it('forgets the password when asked, whatever was typed', async () => {
      const { inDialog, openIt, write, saved, save } = await mountDialog({
        server: mailServer(),
      })
      await openIt()
      await write('mail-password', 'another')
      inDialog('mail-forget')!.querySelector('input')!.click()
      await flushPromises()
      expect(inDialog('mail-password')!.textContent).not.toContain('Saved. Leave this empty')

      await save()

      const answer = saved.mock.calls[0]![0]
      expect(answer.clear_password).toBe(true)
      expect(answer).not.toHaveProperty('password')
    })

    it('shows what is kept each time it opens, not what an earlier visit left', async () => {
      const { inDialog, openIt, write, open } = await mountDialog({ server: mailServer() })
      await openIt()
      await write('mail-host', 'something.else')
      inDialog('mail-forget')!.querySelector('input')!.click()
      open.value = false
      await flushPromises()

      await openIt()

      expect(inDialog('mail-host')!.querySelector('input')!.value).toBe('smtp.example.com')
      expect(inDialog('mail-forget')!.querySelector('input')!.checked).toBe(false)
    })
  })

  it('shows what was wrong with each field', async () => {
    const { inDialog, openIt } = await mountDialog({
      problems: {
        host: "That isn't a server name.",
        port: 'That port is not allowed.',
        sender: 'That is not an email address.',
        password: 'It cannot hold a new line.',
      },
    })

    await openIt()

    expect(inDialog('mail-host')!.textContent).toContain("That isn't a server name.")
    expect(inDialog('mail-port')!.textContent).toContain('That port is not allowed.')
    expect(inDialog('mail-sender')!.textContent).toContain('not an email address')
    expect(inDialog('mail-password')!.textContent).toContain('new line')
  })

  it('shows a failure that is not about a field', async () => {
    const { inDialog, openIt } = await mountDialog({ failure: "Can't reach AresGate." })

    await openIt()

    expect(inDialog('mail-failure')!.textContent).toContain("Can't reach AresGate.")
  })

  it('closes when cancelled', async () => {
    const { inDialog, openIt, open } = await mountDialog()
    await openIt()

    inDialog('mail-cancel')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
  })

  it('cannot be cancelled while it is saving', async () => {
    const { inDialog, openIt } = await mountDialog({ busy: true })

    await openIt()

    expect((inDialog('mail-cancel') as HTMLButtonElement).disabled).toBe(true)
  })

  it('gives the keyboard back to what opened it', async () => {
    const { inDialog, openIt, wrapper, open } = await mountDialog()
    await openIt()
    inDialog('mail-cancel')!.click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 400))

    expect(open.value).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('[data-test="opener"]').element)
  })
})
