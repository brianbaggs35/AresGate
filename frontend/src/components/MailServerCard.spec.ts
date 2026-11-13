import MailServerCard from '@/components/MailServerCard.vue'
import { mailServer, noMailServer } from '@/test/alerts'
import type { MailServer } from '@/api/alerts'
import { mountWithPlugins } from '@/test/mount'

async function show(server: MailServer, props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(MailServerCard, { props: { server, ...props } })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, text: (selector: string) => find(selector).text() }
}

describe('MailServerCard', () => {
  it('says none is set up and offers to set one up', async () => {
    const { text, find, wrapper } = await show(noMailServer())

    expect(text('mail-none')).toContain('No mail server is set up')
    expect(text('mail-edit')).toBe('Set up the mail server')
    expect(find('mail-remove').exists()).toBe(false)
    await find('mail-edit').trigger('click')
    expect(wrapper.emitted('edit')).toHaveLength(1)
  })

  it('shows the server, how it connects, who it signs in as and that a password is kept', async () => {
    const { text } = await show(mailServer())

    expect(text('mail-name')).toBe('smtp.example.com:587')
    expect(text('mail-way')).toBe('STARTTLS')
    expect(text('mail-details')).toBe(
      'Emails come from alerts@example.com. It signs in as alerts@example.com.',
    )
    expect(text('mail-password-kept')).toContain('The password is saved, encrypted.')
    expect(text('mail-edit')).toBe('Change the mail server')
  })

  it('names each way of connecting', async () => {
    const ssl = await show(mailServer({ security: 'ssl', port: 465 }))
    const none = await show(
      mailServer({ security: 'none', port: 25, username: null, password_kept: false }),
    )

    expect(ssl.text('mail-way')).toBe('SSL/TLS')
    expect(none.text('mail-way')).toBe('not encrypted')
  })

  it('says when it signs in with no password or no user name', async () => {
    const noPassword = await show(mailServer({ password_kept: false }))
    const noUser = await show(mailServer({ username: null, password_kept: false }))

    expect(noPassword.text('mail-details')).toContain('as alerts@example.com, with no password.')
    expect(noPassword.find('mail-password-kept').exists()).toBe(false)
    expect(noUser.text('mail-details')).toContain('It signs in with no user name.')
  })

  it('asks to remove it', async () => {
    const { find, wrapper } = await show(mailServer())

    await find('mail-remove').trigger('click')

    expect(wrapper.emitted('remove')).toHaveLength(1)
  })

  it('holds its buttons while it is busy', async () => {
    const { find } = await show(mailServer(), { busy: true })

    expect(find('mail-edit').attributes('disabled')).toBeDefined()
    expect(find('mail-remove').attributes('disabled')).toBeDefined()
  })
})
