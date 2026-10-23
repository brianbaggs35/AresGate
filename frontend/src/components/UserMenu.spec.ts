import { VSnackbar } from 'vuetify/components'

import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import UserMenu from '@/components/UserMenu.vue'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open() {
  const mounted = await mountWithPlugins(UserMenu, {
    withApp: true,
    route: '/settings/account',
    signedIn: 'admin',
  })
  await mounted.wrapper.find('[data-test="user-menu"]').trigger('click')
  await flushPromises()
  return mounted
}

/** The menu opens in an overlay outside the component. */
const item = (name: string) => document.querySelector<HTMLElement>(`[data-test="${name}"]`)

describe('UserMenu', () => {
  it('names the account on its button', async () => {
    const { wrapper } = await mountWithPlugins(UserMenu, { withApp: true, signedIn: 'admin' })
    expect(wrapper.find('[data-test="user-menu"]').attributes('aria-label')).toBe('Account: admin')
  })

  it('says who is signed in, and links to the security page', async () => {
    await open()
    expect(item('user-name')?.textContent).toContain('Signed in as admin')
    expect(item('user-settings')?.getAttribute('href')).toBe('/settings/account')
  })

  it('signs out, and goes to the sign-in page', async () => {
    const logOut = vi.spyOn(authApi, 'logOut').mockResolvedValue()
    const { router } = await open()
    item('sign-out')?.click()
    await flushPromises()
    expect(logOut).toHaveBeenCalledWith('a-security-token')
    expect(useSessionStore().signedIn).toBe(false)
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('sign-in')
    })
  })

  it('says so when it can’t sign out, and stays where it is', async () => {
    vi.spyOn(authApi, 'logOut').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { wrapper, router } = await open()
    item('sign-out')?.click()
    await flushPromises()
    expect(item('sign-out-error')?.textContent).toContain("Can't reach AresGate.")
    expect(useSessionStore().signedIn).toBe(true)
    expect(router.currentRoute.value.name).toBe('settings-account')

    // The message goes away by itself after a few seconds.
    wrapper.findComponent(VSnackbar).vm.$emit('update:modelValue', false)
    await flushPromises()
    expect(wrapper.findComponent(VSnackbar).props('modelValue')).toBe(false)
  })
})
