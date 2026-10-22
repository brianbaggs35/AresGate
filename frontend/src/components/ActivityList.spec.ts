import type { AuditEvent } from '@/api/audit'
import ActivityList from '@/components/ActivityList.vue'
import { mountWithPlugins } from '@/test/mount'

const FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'

function event(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: 1,
    occurred_at: '2026-03-04T15:30:00Z',
    action: 'auth.login_succeeded',
    outcome: 'success',
    username: 'admin',
    client_address: '203.0.113.5',
    user_agent: FIREFOX,
    ...overrides,
  }
}

async function show(...events: AuditEvent[]) {
  const { wrapper } = await mountWithPlugins(ActivityList, { props: { events } })
  return wrapper
}

describe('ActivityList', () => {
  it('lists the events in the order given, as a list', async () => {
    const wrapper = await show(
      event({ id: 2, action: 'auth.logout' }),
      event({ id: 1, action: 'auth.login_succeeded' }),
    )
    expect(wrapper.find('ul').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="activity-title"]').map((title) => title.text())).toEqual([
      'Signed out · admin',
      'Signed in · admin',
    ])
  })

  it('says where each was from', async () => {
    const wrapper = await show(event())
    const detail = wrapper.find('[data-test="activity-detail"]').text()
    expect(detail).toContain('Firefox on Linux')
    expect(detail).toContain('203.0.113.5')
    expect(detail).toMatch(/2026/)
  })

  it('names every kind of event', async () => {
    const actions = [
      'setup.completed',
      'setup.code_rejected',
      'auth.login_succeeded',
      'auth.login_failed',
      'auth.logout',
      'audit.events_purged',
    ]
    const wrapper = await show(
      ...actions.map((action, id) => event({ id, action, username: null })),
    )
    expect(wrapper.findAll('[data-test="activity-title"]').map((title) => title.text())).toEqual([
      'AresGate was set up',
      'Wrong setup code',
      'Signed in',
      'Sign-in failed',
      'Signed out',
      'Old activity was removed',
    ])
  })

  it('shows an event it has no name for as it is', async () => {
    const wrapper = await show(event({ action: 'passkey.added', username: null }))
    expect(wrapper.find('[data-test="activity-title"]').text()).toBe('passkey.added')
  })

  it('marks a failure differently from a success, in words as well as colour', async () => {
    const wrapper = await show(
      event({ id: 2, outcome: 'failure', action: 'auth.login_failed' }),
      event({ id: 1 }),
    )
    const marks = wrapper.findAll('[role="img"]')
    expect(marks.map((mark) => mark.attributes('aria-label'))).toEqual(['Failed', 'Succeeded'])
    // A decorative icon is hidden from screen readers; these say something.
    expect(marks.map((mark) => mark.attributes('aria-hidden'))).toEqual(['false', 'false'])
  })

  it('copes with what it is not told', async () => {
    const wrapper = await show(event({ username: null, client_address: null, user_agent: null }))
    expect(wrapper.find('[data-test="activity-title"]').text()).toBe('Signed in')
    const detail = wrapper.find('[data-test="activity-detail"]').text()
    expect(detail).toContain('Unknown device')
    expect(detail).not.toContain('203.0.113.5')
  })
})
