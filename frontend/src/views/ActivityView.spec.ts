import * as auditApi from '@/api/audit'
import { ApiError } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import ActivityView from '@/views/ActivityView.vue'

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
  const mounted = await mountWithPlugins(ActivityView, {
    route: '/settings/activity',
    signedIn: 'admin',
  })
  await flushPromises()
  return mounted
}

describe('ActivityView', () => {
  it('lists the 20 most recent events', async () => {
    const fetchRecent = vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([recorded])
    const { wrapper } = await open()
    expect(fetchRecent).toHaveBeenCalledWith(20)
    expect(wrapper.findAll('[data-test="activity"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="no-activity"]').exists()).toBe(false)
  })

  it('shows a placeholder while it loads', async () => {
    vi.spyOn(auditApi, 'fetchRecentActivity').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(ActivityView, { signedIn: 'admin' })
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
})
