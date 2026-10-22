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

  describe('the second step', () => {
    async function passwordAccepted(route = '/sign-in') {
      vi.spyOn(authApi, 'logIn').mockResolvedValue({
        two_factor_required: true,
        challenge: 'a-challenge',
      })
      const opened = await open(route)
      await opened.type('username', 'admin')
      await opened.type('password', 'a long enough phrase')
      await opened.submit()
      return opened
    }

    it('asks for a code instead of signing in, and forgets the password', async () => {
      const { wrapper } = await passwordAccepted()
      expect(useSessionStore().signedIn).toBe(false)
      expect(wrapper.find('h1').text()).toBe('Enter a code')
      expect(wrapper.text()).toContain('authenticator app')
      expect(wrapper.find('[data-test="password"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="code"] input').attributes('autocomplete')).toBe(
        'one-time-code',
      )
    })

    it('puts the keyboard in the code field', async () => {
      const { wrapper } = await passwordAccepted()
      expect(document.activeElement).toBe(wrapper.find('[data-test="code"] input').element)
    })

    it('finishes signing in with the code and the challenge, and goes to the front page', async () => {
      const logInWithCode = vi.spyOn(authApi, 'logInWithCode').mockResolvedValue(info)
      const { type, router, submit } = await passwordAccepted()
      await type('code', '123456')
      await submit()
      expect(logInWithCode).toHaveBeenCalledWith('a-challenge', '123456')
      expect(useSessionStore().signedIn).toBe(true)
      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('home')
      })
    })

    it('goes on to the page that was asked for', async () => {
      vi.spyOn(authApi, 'logInWithCode').mockResolvedValue(info)
      const { type, router, submit } = await passwordAccepted('/sign-in?next=/security')
      await type('code', 'K7QD-3MWX-9HPA')
      await submit()
      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('security')
      })
    })

    it('asks for a code before it asks the API', async () => {
      const logInWithCode = vi.spyOn(authApi, 'logInWithCode')
      const { wrapper, submit } = await passwordAccepted()
      await submit()
      expect(wrapper.text()).toContain('Enter a code.')
      expect(logInWithCode).not.toHaveBeenCalled()
    })

    it('says when the code is wrong, and clears it', async () => {
      vi.spyOn(authApi, 'logInWithCode').mockRejectedValue(
        new ApiError(401, "That code isn't right.", 'unauthenticated'),
      )
      const { wrapper, type, submit } = await passwordAccepted()
      await type('code', '000000')
      await submit()
      expect(wrapper.find('[data-test="sign-in-error"]').text()).toBe("That code isn't right.")
      expect(wrapper.find<HTMLInputElement>('[data-test="code"] input').element.value).toBe('')
      expect(wrapper.find('h1').text()).toBe('Enter a code')
      expect(useSessionStore().signedIn).toBe(false)
    })

    it('goes back to the password for a different account, without the earlier error', async () => {
      vi.spyOn(authApi, 'logInWithCode').mockRejectedValue(
        new ApiError(401, "That code isn't right.", 'unauthenticated'),
      )
      const { wrapper, type, submit } = await passwordAccepted()
      await type('code', '000000')
      await submit()
      await wrapper.find('[data-test="start-over"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('h1').text()).toBe('Sign in')
      expect(wrapper.find('[data-test="sign-in-error"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="password"]').exists()).toBe(true)
    })

    it('does not say the sign-in ended while it waits for a code', async () => {
      const { wrapper } = await passwordAccepted()
      useSessionStore().expired = true
      await flushPromises()
      expect(wrapper.find('[data-test="signed-out-notice"]').exists()).toBe(false)
    })
  })
})
