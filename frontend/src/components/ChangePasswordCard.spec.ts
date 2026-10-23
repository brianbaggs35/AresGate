import * as accountApi from '@/api/account'
import { ApiError } from '@/api/client'
import ChangePasswordCard from '@/components/ChangePasswordCard.vue'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const OLD = 'the password until now'
const NEW = 'a brand new phrase'

async function open() {
  const mounted = await mountWithPlugins(ChangePasswordCard, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const type = async (selector: string, value: string) => {
    await find(selector).find('input').setValue(value)
  }
  const submit = async () => {
    await mounted.wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  const fill = async (current = OLD, next = NEW, again = next) => {
    await type('current-password', current)
    await type('new-password', next)
    await type('confirm-new-password', again)
  }
  const value = (selector: string) => find(selector).find<HTMLInputElement>('input').element.value
  return { ...mounted, find, type, submit, fill, value }
}

describe('ChangePasswordCard', () => {
  it('asks for the current password, the new one, and the new one again', async () => {
    const { find } = await open()
    expect(find('password-card').find('h2').text()).toBe('Password')
    expect(find('current-password').text()).toContain('Current password')
    expect(find('new-password').text()).toContain('New password')
    expect(find('confirm-new-password').text()).toContain('Confirm new password')
    expect(find('change-password').text()).toBe('Change password')
    expect(find('password-changed').exists()).toBe(false)
    expect(find('password-error').exists()).toBe(false)
  })

  it('changes it, and says how many other sign-ins that ended', async () => {
    const change = vi.spyOn(accountApi, 'changePassword').mockResolvedValue({ ended: 2 })
    const { find, fill, submit, value } = await open()

    await fill()
    await submit()

    expect(change).toHaveBeenCalledWith(OLD, NEW, TOKEN)
    expect(find('password-changed').text()).toBe(
      'Your password was changed, and 2 other sign-ins were ended.',
    )
    // What was typed is not left behind.
    expect(value('current-password')).toBe('')
    expect(value('new-password')).toBe('')
    expect(value('confirm-new-password')).toBe('')
  })

  it('says so when it ended one sign-in, and when it ended none', async () => {
    const change = vi.spyOn(accountApi, 'changePassword').mockResolvedValue({ ended: 1 })
    const { find, fill, submit } = await open()

    await fill()
    await submit()
    expect(find('password-changed').text()).toBe(
      'Your password was changed, and 1 other sign-in was ended.',
    )

    change.mockResolvedValue({ ended: 0 })
    await fill()
    await submit()
    expect(find('password-changed').text()).toBe('Your password was changed.')
  })

  it('asks for what is missing before asking the API', async () => {
    const change = vi.spyOn(accountApi, 'changePassword')
    const { find, submit } = await open()

    await submit()

    expect(find('current-password').text()).toContain('Enter your current password.')
    expect(find('new-password').text()).toContain('Use 12 to 128 characters.')
    expect(change).not.toHaveBeenCalled()
  })

  it('says when the new password is too long', async () => {
    const change = vi.spyOn(accountApi, 'changePassword')
    const { find, fill, submit } = await open()

    await fill(OLD, 'x'.repeat(129))
    await submit()

    expect(find('new-password').text()).toContain('Use 12 to 128 characters.')
    expect(change).not.toHaveBeenCalled()
  })

  it('says when the two new passwords differ', async () => {
    const change = vi.spyOn(accountApi, 'changePassword')
    const { find, fill, submit } = await open()

    await fill(OLD, NEW, 'something else entirely')
    await submit()

    expect(find('confirm-new-password').text()).toContain("The passwords don't match.")
    expect(change).not.toHaveBeenCalled()
  })

  it('points at the current password when that was not right, and clears it when it changes', async () => {
    vi.spyOn(accountApi, 'changePassword').mockRejectedValue(
      new ApiError(403, "The password isn't right.", 'forbidden'),
    )
    const { find, fill, submit, type } = await open()

    await fill()
    await submit()
    expect(find('current-password').text()).toContain("The password isn't right.")
    expect(find('password-error').exists()).toBe(false)
    // Nothing was lost, so it can be tried again.
    expect(find('new-password').find<HTMLInputElement>('input').element.value).toBe(NEW)

    await type('current-password', 'another try')
    expect(find('current-password').text()).not.toContain("The password isn't right.")
  })

  it('points at the new password when the API would not accept it, and clears it when it changes', async () => {
    vi.spyOn(accountApi, 'changePassword').mockRejectedValue(
      new ApiError(422, 'That password is too easy to guess.', 'invalid'),
    )
    const { find, fill, submit, type } = await open()

    await fill()
    await submit()
    expect(find('new-password').text()).toContain('That password is too easy to guess.')

    await type('new-password', 'a different phrase')
    expect(find('new-password').text()).not.toContain('too easy to guess')
  })

  it('says why it could not, when no field is to blame', async () => {
    vi.spyOn(accountApi, 'changePassword').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { find, fill, submit } = await open()

    await fill()
    await submit()

    expect(find('password-error').text()).toBe("Can't reach AresGate.")
    expect(find('password-changed').exists()).toBe(false)
  })

  it('forgets an earlier result when it is submitted again', async () => {
    const change = vi.spyOn(accountApi, 'changePassword').mockResolvedValue({ ended: 0 })
    const { find, fill, submit } = await open()
    await fill()
    await submit()
    expect(find('password-changed').exists()).toBe(true)

    change.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
    await fill()
    await submit()

    expect(find('password-changed').exists()).toBe(false)
    expect(find('password-error').exists()).toBe(true)
  })

  it('notes that the sign-in ended when the API says nobody is signed in', async () => {
    vi.spyOn(accountApi, 'changePassword').mockRejectedValue(
      new ApiError(401, "You're not signed in.", 'unauthenticated'),
    )
    const { fill, submit } = await open()

    await fill()
    await submit()

    expect(useSessionStore()).toMatchObject({ signedIn: false, expired: true })
  })
})
