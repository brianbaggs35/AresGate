import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import * as passkeysApi from '@/api/passkeys'
import * as twoFactorApi from '@/api/two-factor'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AccountView from '@/views/AccountView.vue'

async function open() {
  vi.spyOn(passkeysApi, 'fetchPasskeys').mockResolvedValue([])
  vi.spyOn(twoFactorApi, 'fetchTwoFactorStatus').mockResolvedValue({
    enabled: false,
    recovery_codes_left: 0,
  })
  const mounted = await mountWithPlugins(AccountView, {
    route: '/settings/account',
    signedIn: 'admin',
  })
  await flushPromises()
  return mounted
}

describe('AccountView', () => {
  it('says who is signed in', async () => {
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="account-name"]').text()).toBe('admin')
  })

  it('has the cards for the password, passkeys and two-step verification after the account', async () => {
    const { wrapper } = await open()
    const cards = wrapper
      .findAll('[data-test$="-card"]')
      .map((card) => card.attributes('data-test'))
    expect(cards).toEqual(['account-card', 'password-card', 'passkeys-card', 'two-factor-card'])
  })

  it('signs out, and goes to the sign-in page', async () => {
    const logOut = vi.spyOn(authApi, 'logOut').mockResolvedValue()
    const { wrapper, router } = await open()
    await wrapper.find('[data-test="sign-out-here"]').trigger('click')
    await flushPromises()
    expect(logOut).toHaveBeenCalledWith('a-security-token')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('sign-in')
    })
  })

  it('says so when it can’t sign out, and stays where it is', async () => {
    vi.spyOn(authApi, 'logOut').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { wrapper, router } = await open()
    await wrapper.find('[data-test="sign-out-here"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="sign-out-here-error"]').text()).toBe("Can't reach AresGate.")
    expect(router.currentRoute.value.name).toBe('settings-account')
  })
})
