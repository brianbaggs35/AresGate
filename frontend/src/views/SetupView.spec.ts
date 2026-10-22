import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import SetupView from '@/views/SetupView.vue'

const info = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }
const CODE = 'K7QD-3MWX-9HPA'
const PASSWORD = 'a long enough phrase'

async function open() {
  const mounted = await mountWithPlugins(SetupView, {
    route: '/setup',
    beforeMount: () => {
      useSessionStore().setupRequired = true
    },
  })
  const { wrapper } = mounted
  const type = async (selector: string, value: string) =>
    wrapper.find(`[data-test="${selector}"] input`).setValue(value)
  const submit = async () => {
    await wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  const toAccount = async (code = CODE) => {
    await type('setup-code', code)
    await submit()
  }
  const fillAccount = async (username = 'admin', password = PASSWORD, confirmation = password) => {
    await type('username', username)
    await type('password', password)
    await type('confirm-password', confirmation)
  }
  return { ...mounted, type, submit, toAccount, fillAccount }
}

describe('SetupView', () => {
  describe('step 1, the setup code', () => {
    it('starts by asking for the code in the log, and says where to find it', async () => {
      const { wrapper } = await open()
      expect(wrapper.find('h1').text()).toBe('Set up AresGate')
      expect(wrapper.text()).toContain('Step 1 of 2')
      expect(wrapper.text()).toContain('make logs')
      expect(wrapper.find('[data-test="setup-code"] input').exists()).toBe(true)
      expect(wrapper.find('[data-test="username"]').exists()).toBe(false)
    })

    it('asks for twelve letters and numbers before moving on', async () => {
      const { wrapper, submit, type } = await open()
      await submit()
      expect(wrapper.text()).toContain('The code is 12 letters and numbers')
      await type('setup-code', 'K7QD-3MWX')
      await submit()
      expect(wrapper.text()).toContain('Step 1 of 2')
    })

    it.each(['K7QD-3MWX-9HPA', 'k7qd 3mwx 9hpa', 'K7QD3MWX9HPA'])(
      'takes the code written as %s',
      async (code) => {
        const { wrapper, toAccount } = await open()
        await toAccount(code)
        expect(wrapper.text()).toContain('Step 2 of 2')
      },
    )
  })

  describe('step 2, the account', () => {
    it('asks for a username and a password twice, with the hints password managers need', async () => {
      const { wrapper, toAccount } = await open()
      await toAccount()
      expect(wrapper.find('[data-test="username"] input').attributes('autocomplete')).toBe(
        'username',
      )
      expect(wrapper.find('[data-test="password"] input').attributes('autocomplete')).toBe(
        'new-password',
      )
      expect(wrapper.find('[data-test="confirm-password"] input').attributes('autocomplete')).toBe(
        'new-password',
      )
    })

    it('can go back to the code, which is still there', async () => {
      const { wrapper, toAccount } = await open()
      await toAccount()
      await wrapper.find('[data-test="back"]').trigger('click')
      expect(wrapper.text()).toContain('Step 1 of 2')
      expect(wrapper.find<HTMLInputElement>('[data-test="setup-code"] input').element.value).toBe(
        CODE,
      )
    })

    it('checks what it can before asking the API', async () => {
      const setUp = vi.spyOn(authApi, 'setUp')
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount('x', 'short', 'different')
      await submit()
      expect(wrapper.text()).toContain('Use 3 to 64 letters, numbers')
      expect(wrapper.text()).toContain('Use 12 to 128 characters')
      expect(wrapper.text()).toContain("The passwords don't match.")
      expect(setUp).not.toHaveBeenCalled()
    })

    it('refuses a password of more than 128 characters', async () => {
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount('admin', 'a'.repeat(129))
      await submit()
      expect(wrapper.text()).toContain('Use 12 to 128 characters')
    })

    it('creates the account, signs in, and goes to the front page', async () => {
      const setUp = vi.spyOn(authApi, 'setUp').mockResolvedValue(info)
      const { toAccount, fillAccount, submit, router } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(setUp).toHaveBeenCalledWith({ code: CODE, username: 'admin', password: PASSWORD })
      expect(useSessionStore().signedIn).toBe(true)
      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('home')
      })
    })

    it('shows why the API refused a password, and keeps what was typed', async () => {
      vi.spyOn(authApi, 'setUp').mockRejectedValue(
        new ApiError(422, 'That password is too easy to guess. Try a longer phrase.', 'invalid'),
      )
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(wrapper.find('[data-test="setup-error"]').text()).toContain('too easy to guess')
      expect(wrapper.text()).toContain('Step 2 of 2')
      expect(wrapper.find<HTMLInputElement>('[data-test="username"] input').element.value).toBe(
        'admin',
      )
    })

    it('goes back to the code when the API says it is wrong', async () => {
      vi.spyOn(authApi, 'setUp').mockRejectedValue(
        new ApiError(403, "That setup code isn't right.", 'forbidden'),
      )
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(wrapper.text()).toContain('Step 1 of 2')
      expect(wrapper.find('[data-test="setup-error"]').text()).toBe("That setup code isn't right.")
    })

    it('says so when there is a wait', async () => {
      vi.spyOn(authApi, 'setUp').mockRejectedValue(
        new ApiError(429, 'Too many attempts. Try again in 2 minutes.', 'rate_limited'),
      )
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(wrapper.find('[data-test="setup-error"]').text()).toContain('Try again in 2 minutes')
      expect(wrapper.text()).toContain('Step 2 of 2')
    })

    it('goes to the sign-in page when someone else already set AresGate up', async () => {
      vi.spyOn(authApi, 'setUp').mockRejectedValue(
        new ApiError(409, 'AresGate is already set up.', 'conflict'),
      )
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
      vi.spyOn(authApi, 'fetchSession').mockRejectedValue(
        new ApiError(401, "You're not signed in.", 'unauthenticated'),
      )
      const { toAccount, fillAccount, submit, router } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('sign-in')
      })
    })

    it('stays and explains when there is no setup code to use', async () => {
      const message = 'There is no setup code. Restart AresGate and look in its log for a new one.'
      vi.spyOn(authApi, 'setUp').mockRejectedValue(new ApiError(409, message, 'conflict'))
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(true)
      const { wrapper, toAccount, fillAccount, submit, router } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(wrapper.find('[data-test="setup-error"]').text()).toBe(message)
      expect(router.currentRoute.value.name).toBe('setup')
    })

    it('stays and explains when the API can’t be reached', async () => {
      vi.spyOn(authApi, 'setUp').mockRejectedValue(new Error('offline'))
      const { wrapper, toAccount, fillAccount, submit } = await open()
      await toAccount()
      await fillAccount()
      await submit()
      expect(wrapper.find('[data-test="setup-error"]').text()).toBe('offline')
      expect(wrapper.text()).toContain('Step 2 of 2')
    })
  })
})
