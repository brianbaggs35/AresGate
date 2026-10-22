import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import SignInView from '@/views/SignInView.vue'

const info = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }

async function open(route = '/sign-in') {
  const mounted = await mountWithPlugins(SignInView, { route })
  const type = async (selector: string, value: string) =>
    mounted.wrapper.find(`[data-test="${selector}"] input`).setValue(value)
  const submit = async () => {
    await mounted.wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  return { ...mounted, type, submit }
}

describe('SignInView', () => {
  it('asks for a username and a password, with the hints password managers need', async () => {
    const { wrapper } = await open()
    expect(wrapper.find('h1').text()).toBe('Sign in')
    expect(wrapper.find('[data-test="username"] input').attributes('autocomplete')).toBe('username')
    expect(wrapper.find('[data-test="password"] input').attributes('autocomplete')).toBe(
      'current-password',
    )
  })

  it('signs in, and goes to the front page', async () => {
    const logIn = vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
    const { type, submit, router } = await open()
    await type('username', 'admin')
    await type('password', 'a long enough phrase')
    await submit()
    expect(logIn).toHaveBeenCalledWith({ username: 'admin', password: 'a long enough phrase' })
    expect(useSessionStore().signedIn).toBe(true)
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('home')
    })
  })

  it('goes on to the page that was asked for', async () => {
    vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
    const { type, submit, router } = await open('/sign-in?next=/security')
    await type('username', 'admin')
    await type('password', 'a long enough phrase')
    await submit()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('security')
    })
  })

  it('asks for both before it asks the API', async () => {
    const logIn = vi.spyOn(authApi, 'logIn')
    const { wrapper, type, submit } = await open()
    await submit()
    expect(wrapper.text()).toContain('Enter your username.')
    expect(wrapper.text()).toContain('Enter your password.')

    await type('username', '   ')
    await submit()
    expect(wrapper.text()).toContain('Enter your username.')
    expect(logIn).not.toHaveBeenCalled()
  })

  it('says what went wrong, and clears the password', async () => {
    vi.spyOn(authApi, 'logIn').mockRejectedValue(
      new ApiError(401, 'Incorrect username or password.', 'unauthenticated'),
    )
    const { wrapper, type, submit } = await open()
    await type('username', 'admin')
    await type('password', 'not the password')
    await submit()
    expect(wrapper.find('[data-test="sign-in-error"]').text()).toBe(
      'Incorrect username or password.',
    )
    expect(wrapper.find<HTMLInputElement>('[data-test="password"] input').element.value).toBe('')
    expect(useSessionStore().signedIn).toBe(false)
  })

  it('says how long to wait when the account is locked', async () => {
    vi.spyOn(authApi, 'logIn').mockRejectedValue(
      new ApiError(429, 'Too many attempts. Try again in 1 minute.', 'rate_limited'),
    )
    const { wrapper, type, submit } = await open()
    await type('username', 'admin')
    await type('password', 'a long enough phrase')
    await submit()
    expect(wrapper.find('[data-test="sign-in-error"]').text()).toBe(
      'Too many attempts. Try again in 1 minute.',
    )
  })

  it('says when a sign-in ended while the page was open', async () => {
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="signed-out-notice"]').exists()).toBe(false)
    useSessionStore().expired = true
    await flushPromises()
    expect(wrapper.find('[data-test="signed-out-notice"]').text()).toContain('Your sign-in ended')
  })

  it('shows the error instead of that notice once there is one', async () => {
    vi.spyOn(authApi, 'logIn').mockRejectedValue(new ApiError(401, 'Incorrect.', 'unauthenticated'))
    const { wrapper, type, submit } = await open()
    useSessionStore().expired = true
    await type('username', 'admin')
    await type('password', 'x')
    await submit()
    expect(wrapper.find('[data-test="signed-out-notice"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="sign-in-error"]').exists()).toBe(true)
  })
})
