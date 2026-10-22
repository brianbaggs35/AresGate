import * as auditApi from '@/api/audit'
import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import * as twoFactorApi from '@/api/two-factor'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import SecurityView from '@/views/SecurityView.vue'

const recorded: auditApi.AuditEvent = {
  id: 1,
  occurred_at: '2026-03-04T15:30:00Z',
  action: 'auth.login_succeeded',
  outcome: 'success',
  username: 'admin',
  client_address: '203.0.113.5',
  user_agent: null,
}

async function open() {
  vi.spyOn(twoFactorApi, 'fetchTwoFactorStatus').mockResolvedValue({
    enabled: false,
    recovery_codes_left: 0,
  })
  const mounted = await mountWithPlugins(SecurityView, { route: '/security', signedIn: 'admin' })
  await flushPromises()
  return mounted
}

describe('SecurityView', () => {
  it('says who is signed in', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="account-name"]').text()).toBe('admin')
  })

  it('lists the 20 most recent events', async () => {
    const fetchRecent = vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([recorded])
    const { wrapper } = await open()
    expect(fetchRecent).toHaveBeenCalledWith(20)
    expect(wrapper.findAll('[data-test="activity"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="no-activity"]').exists()).toBe(false)
  })

  it('has the card for two-step verification between the account and the activity', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
    const { wrapper } = await open()
    const cards = wrapper
      .findAll('[data-test$="-card"]')
      .map((card) => card.attributes('data-test'))
    expect(cards).toEqual(['account-card', 'two-factor-card', 'activity-card'])
  })

  it('shows a placeholder while it loads', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(SecurityView, { signedIn: 'admin' })
    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('says when there is nothing to list', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="no-activity"]').exists()).toBe(true)
  })

  it('says why it can’t list them, and tries again when asked', async () => {
    const fetchRecent = vi
      .spyOn(auditApi, 'fetchRecentActivity')
      .mockRejectedValueOnce(new ApiError(0, "Can't reach AresGate.", 'offline'))
    fetchRecent.mockResolvedValue([recorded])
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="activity-error"]').text()).toBe("Can't reach AresGate.")

    await wrapper.find('[data-test="refresh-activity"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="activity-error"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="activity"]')).toHaveLength(1)
  })

  it('notes that the sign-in ended when the API says nobody is signed in', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockRejectedValue(
      new ApiError(401, "You're not signed in.", 'unauthenticated'),
    )
    await open()
    expect(useSessionStore()).toMatchObject({ signedIn: false, expired: true })
  })

  it('signs out, and goes to the sign-in page', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
    const logOut = vi.spyOn(authApi, 'logOut').mockResolvedValue()
    const { wrapper, router } = await open()
    await wrapper.find('[data-test="sign-out-here"]').trigger('click')
    await flushPromises()
    expect(logOut).toHaveBeenCalledWith('a-security-token')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('sign-in')
    })
  })

  it('says so when it can’t sign out', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
    vi.spyOn(authApi, 'logOut').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { wrapper, router } = await open()
    await wrapper.find('[data-test="sign-out-here"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain("Can't reach AresGate.")
    expect(router.currentRoute.value.name).toBe('security')
  })
})
