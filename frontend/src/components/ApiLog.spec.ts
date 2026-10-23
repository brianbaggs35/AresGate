import { nextTick } from 'vue'
import { VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { Call, CallPage } from '@/api/integrations'
import ApiLog from '@/components/ApiLog.vue'
import { call } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const page = (calls: Call[], next: number | null = null): CallPage => ({
  calls,
  next_before: next,
})
const ONE = [{ key: 'api', label: 'REST API' }]
const TWO = [
  { key: 'api', label: 'OPNsense API' },
  { key: 'zenarmor', label: 'Zenarmor API' },
]

async function open(
  first: CallPage | Error = page([call()]),
  { connections = ONE, refresh = 0 }: { connections?: typeof ONE; refresh?: number } = {},
) {
  const fetch = vi.spyOn(integrationsApi, 'fetchCalls')
  if (first instanceof Error) fetch.mockRejectedValue(first)
  else fetch.mockResolvedValue(first)
  const mounted = await mountWithPlugins(ApiLog, {
    signedIn: 'admin',
    props: { integration: 'ntopng', connections, refresh },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const rows = () => mounted.wrapper.findAll('[data-test="log-call"]')
  const choose = async (filter: string, value: string) => {
    mounted.wrapper
      .findAllComponents(VSelect)
      .find((select) => select.attributes('data-test') === `filter-${filter}`)
      ?.vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, fetch, find, rows, choose, click }
}

describe('ApiLog', () => {
  it('asks for the newest requests of the integration', async () => {
    const { fetch } = await open()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith('ntopng', { limit: 25 })
  })

  it('shows what each request was, when it was, how it ended and how long it took', async () => {
    const { rows } = await open(
      page([
        call({ id: 2, method: 'POST', path: '/security/user/authenticate', status_code: 201 }),
        call({ id: 1, duration_ms: 1234 }),
      ]),
    )
    expect(rows()).toHaveLength(2)
    const [newest, oldest] = rows()
    expect(newest?.find('[data-test="call-method"]').text()).toBe('POST')
    expect(newest?.find('[data-test="call-path"]').text()).toBe('/security/user/authenticate')
    expect(newest?.find('[data-test="call-detail"]').text()).toMatch(/2026.*· 201 · 42 ms/)
    expect(oldest?.find('[data-test="call-detail"]').text()).toContain('1234 ms')
    expect(oldest?.find('time').attributes('datetime')).toBe('2026-03-04T15:30:45Z')
  })

  it('marks one that worked and one that failed, in words as well as colour', async () => {
    const { rows } = await open(
      page([
        call({ id: 2, status_code: 403, error: 'Forbidden' }),
        call({ id: 1, status_code: null, error: "Couldn't connect to 192.168.1.2:3000." }),
        call({ id: 0 }),
      ]),
    )
    const marks = rows().map((row) => row.find('[role="img"]').attributes('aria-label'))
    expect(marks).toEqual(['Failed', 'Failed', 'Worked'])
    expect(rows()[0]?.find('[data-test="call-error"]').text()).toBe('Forbidden')
    expect(rows()[1]?.find('[data-test="call-detail"]').text()).toContain('No answer')
    expect(rows()[2]?.find('[data-test="call-error"]').exists()).toBe(false)
  })

  it('shows what a system said as plain text, never as markup', async () => {
    const hostile = '<img src=x onerror=alert(1)> <script>alert(2)</script>'
    const { wrapper, rows } = await open(page([call({ status_code: 500, error: hostile })]))
    expect(rows()[0]?.find('[data-test="call-error"]').text()).toBe(hostile)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('names the connection of each request when there are several', async () => {
    const { rows } = await open(
      page([call({ id: 2, connection: 'zenarmor' }), call({ id: 1, connection: 'gone' })]),
      { connections: TWO },
    )
    expect(rows()[0]?.find('[data-test="call-detail"]').text()).toContain('Zenarmor API')
    expect(rows()[1]?.find('[data-test="call-detail"]').text()).toContain('gone')
  })

  it('does not name the connection when there is only one', async () => {
    const { rows } = await open()
    expect(rows()[0]?.find('[data-test="call-detail"]').text()).not.toContain('REST API')
  })

  describe('the filters', () => {
    it('has a filter for the connection only when there are several', async () => {
      const one = await open()
      expect(one.find('filter-connection').exists()).toBe(false)
      const two = await open(page([]), { connections: TWO })
      expect(two.find('filter-connection').exists()).toBe(true)
    })

    it('narrows to a connection', async () => {
      const { fetch, choose } = await open(page([call()]), { connections: TWO })
      await choose('connection', 'zenarmor')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, connection: 'zenarmor' })
    })

    it('narrows to the requests that failed, or the ones that worked', async () => {
      const { fetch, choose } = await open()
      await choose('result', 'failed')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, failed: true })
      await choose('result', 'ok')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, failed: false })
      await choose('result', 'all')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25 })
    })

    it('narrows to a method', async () => {
      const { fetch, choose } = await open()
      await choose('method', 'POST')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, method: 'POST' })
    })

    it('narrows to a period of time', async () => {
      const { fetch, choose } = await open()
      const before = Date.now()
      await choose('period', 'day')
      const asked = fetch.mock.lastCall?.[1]
      const since = Date.parse(asked?.since ?? '')
      expect(since).toBeGreaterThanOrEqual(before - 24 * 3_600_000)
      expect(since).toBeLessThanOrEqual(Date.now() - 24 * 3_600_000 + 1000)
      await choose('period', 'hour')
      expect(Date.now() - Date.parse(fetch.mock.lastCall?.[1]?.since ?? '')).toBeLessThan(
        3_600_000 + 1000,
      )
      await choose('period', 'week')
      expect(Date.now() - Date.parse(fetch.mock.lastCall?.[1]?.since ?? '')).toBeGreaterThan(
        6 * 24 * 3_600_000,
      )
    })

    it('says so when nothing matches, and offers to clear them', async () => {
      const { fetch, find, choose, click } = await open()
      fetch.mockResolvedValue(page([]))
      await choose('result', 'failed')
      expect(find('log-empty').text()).toContain('No requests match these filters.')

      fetch.mockResolvedValue(page([call()]))
      await click('log-clear')

      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25 })
      expect(find('log-empty').exists()).toBe(false)
      expect(find('filter-result').text()).toContain('Any result')
    })
  })

  describe('older requests', () => {
    it('are shown after the others when asked for', async () => {
      const { fetch, find, rows, click } = await open(page([call({ id: 30 })], 30))
      fetch.mockResolvedValue(page([call({ id: 5, path: '/older' })], null))

      await click('log-older')

      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, before: 30 })
      expect(rows().map((row) => row.find('[data-test="call-path"]').text())).toEqual([
        '/lua/rest/v2/get/ntopng/interfaces.lua',
        '/older',
      ])
      expect(find('log-older').exists()).toBe(false)
    })

    it('keep the filters', async () => {
      const { fetch, choose, click } = await open(page([call({ id: 30 })], 30))
      await choose('method', 'GET')
      fetch.mockResolvedValue(page([call({ id: 30 })], 30))
      await choose('method', 'GET')
      await click('log-older')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25, method: 'GET', before: 30 })
    })

    it('are not offered when the page was the last', async () => {
      const { find } = await open(page([call()], null))
      expect(find('log-older').exists()).toBe(false)
    })
  })

  describe('reloading', () => {
    it('starts again from the newest when refreshed', async () => {
      const { fetch, click, rows } = await open(page([call({ id: 1 })]))
      fetch.mockResolvedValue(page([call({ id: 2 }), call({ id: 1 })]))
      await click('log-refresh')
      expect(fetch).toHaveBeenLastCalledWith('ntopng', { limit: 25 })
      expect(rows()).toHaveLength(2)
    })

    it('reloads when something happened that made requests', async () => {
      const { fetch, wrapper, rows } = await open(page([call({ id: 1 })]))
      fetch.mockResolvedValue(page([call({ id: 2 }), call({ id: 1 })]))
      await wrapper.setProps({ refresh: 1 })
      await flushPromises()
      expect(fetch).toHaveBeenCalledTimes(2)
      expect(rows()).toHaveLength(2)
    })

    it('ignores an answer that arrives after a newer one', async () => {
      const { fetch, find, rows, choose } = await open(page([call({ id: 1 })]))
      let finishSlow: (value: CallPage) => void = () => {}
      fetch.mockReturnValueOnce(
        new Promise<CallPage>((resolve) => {
          finishSlow = resolve
        }),
      )
      await choose('method', 'GET')
      fetch.mockResolvedValue(page([call({ id: 3, path: '/newest' })]))
      await choose('method', 'POST')

      finishSlow(page([call({ id: 2, path: '/stale' })]))
      await flushPromises()
      await nextTick()

      expect(rows().map((row) => row.find('[data-test="call-path"]').text())).toEqual(['/newest'])
      expect(find('log-error').exists()).toBe(false)
    })
  })

  it('ignores a failure that arrives after a newer answer', async () => {
    const { fetch, find, rows, choose } = await open(page([call({ id: 1 })]))
    let failSlow: (error: Error) => void = () => {}
    fetch.mockReturnValueOnce(
      new Promise<CallPage>((_resolve, reject) => {
        failSlow = reject
      }),
    )
    await choose('method', 'GET')
    fetch.mockResolvedValue(page([call({ id: 3, path: '/newest' })]))
    await choose('method', 'POST')

    failSlow(new Error('Too late.'))
    await flushPromises()

    expect(rows().map((row) => row.find('[data-test="call-path"]').text())).toEqual(['/newest'])
    expect(find('log-error').exists()).toBe(false)
  })

  describe('when it goes wrong', () => {
    it('says why the log could not be read, and tries again', async () => {
      const { fetch, find, click, rows } = await open(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      expect(find('log-error').text()).toContain("Can't reach AresGate.")
      expect(find('log-calls').exists()).toBe(false)

      fetch.mockResolvedValue(page([call()]))
      await click('log-retry')

      expect(find('log-error').exists()).toBe(false)
      expect(rows()).toHaveLength(1)
    })

    it('says why older requests could not be read, and keeps the ones it has', async () => {
      const { fetch, find, click, rows } = await open(page([call()], 9))
      fetch.mockRejectedValue(new ApiError(500, 'AresGate ran into a problem.', 'error'))
      await click('log-older')
      expect(find('log-error').text()).toContain('AresGate ran into a problem.')
      expect(rows()).toHaveLength(1)
    })

    it('says so when the sign-in has ended', async () => {
      const { fetch, find, pinia } = await open()
      fetch.mockRejectedValue(new ApiError(401, 'Sign in first.', 'unauthenticated'))
      await find('log-refresh').trigger('click')
      await flushPromises()
      const { useSessionStore } = await import('@/stores/session')
      expect(useSessionStore(pinia).expired).toBe(true)
      expect(find('log-error').text()).toContain('Sign in first.')
    })
  })

  it('says so when AresGate has not made a request yet', async () => {
    const { find } = await open(page([]))
    expect(find('log-empty').text()).toBe("AresGate hasn't made a request to this system yet.")
    expect(find('log-clear').exists()).toBe(false)
  })

  it('shows placeholders while the first requests load', async () => {
    const fetch = vi
      .spyOn(integrationsApi, 'fetchCalls')
      .mockReturnValue(new Promise<CallPage>(() => {}))
    const { wrapper } = await mountWithPlugins(ApiLog, {
      signedIn: 'admin',
      props: { integration: 'ntopng', connections: ONE, refresh: 0 },
    })
    expect(fetch).toHaveBeenCalledOnce()
    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
    expect(wrapper.find('[data-test="log-calls"]').exists()).toBe(false)
  })
})
