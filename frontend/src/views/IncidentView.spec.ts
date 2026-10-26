import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import { useSessionStore } from '@/stores/session'
import { detail, incident, signal } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import IncidentView from '@/views/IncidentView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const MINUTE = 60_000

interface Options {
  found?: incidentsApi.IncidentDetail | Error
}

async function open({ found = detail() }: Options = {}) {
  const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
  if (found instanceof Error) fetchIncident.mockRejectedValue(found)
  else fetchIncident.mockResolvedValue(found)
  const setStatus = vi.spyOn(incidentsApi, 'setIncidentStatus')
  const mounted = await mountWithPlugins(IncidentView, {
    signedIn: 'admin',
    withApp: true,
    route: '/incidents/1',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, fetchIncident, setStatus, find, text }
}

describe('IncidentView', () => {
  it('asks for the incident that is in the address of the page', async () => {
    const { fetchIncident } = await open()

    expect(fetchIncident).toHaveBeenCalledTimes(1)
    expect(fetchIncident).toHaveBeenCalledWith(1)
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(incidentsApi, 'fetchIncident').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IncidentView, {
      signedIn: 'admin',
      route: '/incidents/1',
    })

    expect(wrapper.find('[data-test="incident-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="tiles"]').exists()).toBe(false)
  })

  describe('the top of the page', () => {
    it('names the incident and leads back to the list', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('h1').text()).toBe('Brute force on ssh (93.184.216.34)')
      const back = wrapper.find('a[href="/incidents"]')
      expect(back.text()).toContain('Incidents')
    })

    it('says how serious it is, what became of it and how sure AresGate is', async () => {
      const { wrapper, text } = await open()

      expect(wrapper.find('[data-test="severity"]').text()).toBe('High')
      expect(wrapper.find('[data-test="incident-status"]').text()).toBe('Open')
      expect(text('confidence-chip')).toBe('High confidence')
    })

    it('says when it began and when it last did something', async () => {
      const { text } = await open()

      expect(text('incident-when')).toMatch(/^First signal .+, the last 2 minutes ago\.$/)
    })

    it('says what its status means', async () => {
      const { text } = await open()

      expect(text('incident-meaning')).toBe("Open: Nobody has said they're looking at it.")
    })

    it('says when its status was set, once someone set it', async () => {
      const changed = new Date(Date.now() - 5 * MINUTE).toISOString()
      const { text } = await open({
        found: detail({ status: 'investigating', status_changed_at: changed }),
      })

      expect(text('incident-meaning')).toBe(
        "Investigating: You're looking into it. Set 5 minutes ago.",
      )
    })
  })

  describe('the tiles', () => {
    it('count the signals, and say over how long they came in', async () => {
      const { text } = await open()

      expect(text('tile-signals')).toContain('Signals')
      expect(text('tile-signals')).toContain('3')
      expect(text('tile-signals')).toContain('over 18m')
    })

    it('name the programs that saw it', async () => {
      const { text } = await open()

      expect(text('tile-programs')).toContain('2')
      expect(text('tile-programs')).toContain('OPNsense, Wazuh')
    })

    it('count the addresses, and how many of them are devices on the network', async () => {
      const { text } = await open()

      expect(text('tile-addresses')).toContain('2')
      expect(text('tile-addresses')).toContain('1 on your network')
    })

    it('say when there is only the one address', async () => {
      const { text } = await open({
        found: detail({ addresses: ['93.184.216.34'], devices: [] }),
      })

      expect(text('tile-addresses')).toContain('Only the one it is about')
    })

    it('count the firewall blocks of its address around then', async () => {
      const { text } = await open({ found: detail({ blocked: 1_250 }) })

      expect(text('tile-blocked')).toContain('1,250')
      expect(text('tile-blocked')).toContain('Of its address, around then')
    })

    it('say there are none to count when it is about a rule, with no address', async () => {
      const { text } = await open({
        found: detail({ blocked: null, subject: 'rule:wazuh:5710', addresses: [] }),
      })

      expect(text('tile-blocked')).toContain('None')
      expect(text('tile-blocked')).toContain('It is about a rule')
    })
  })

  describe('the reasons, the addresses and the timeline', () => {
    it('add up the reasons for the confidence', async () => {
      const { text } = await open()

      expect(text('reasons-card')).toContain('Why AresGate is this sure')
      expect(text('reasons-card')).toContain('Most serious signal')
      expect(text('reasons-card')).toContain('Other programs agree')
      expect(text('reasons-card')).toContain('It keeps happening')
    })

    it('name the devices behind the addresses', async () => {
      const { text } = await open()

      expect(text('addresses-card')).toContain('On your network')
      expect(text('addresses-card')).toContain('nas')
      expect(text('addresses-card')).toContain('Not a device AresGate knows.')
    })

    it('list every signal, oldest first', async () => {
      const { wrapper, text } = await open()

      expect(text('timeline-card')).toContain('Timeline')
      expect(wrapper.findAll('[data-test="signal"]')).toHaveLength(3)
    })
  })

  describe('the chart of signals over time', () => {
    it('counts them by program, and says how wide a bar is', async () => {
      const { wrapper, text } = await open()

      expect(text('spread-card')).toContain('Signals over time')
      expect(text('spread-card')).toContain(
        'Signals in each 1 minute, by the program that reported them.',
      )
      const labels = wrapper.findAll('[data-test="spread-card"] [data-test="chart-legend-label"]')
      expect(labels.map((label) => label.text())).toEqual(['OPNsense', 'Wazuh'])
    })

    it('says it only counts those that are listed when more were kept out', async () => {
      const { text } = await open({ found: detail({ signal_count: 1_500 }) })

      expect(text('spread-card')).toContain('Only those listed below.')
    })

    it('is left out when a single signal makes no story over time', async () => {
      const { find } = await open({
        found: detail({ signal_count: 1, signals: [signal()] }),
      })

      expect(find('spread-card').exists()).toBe(false)
    })
  })

  describe('what can be done', () => {
    it.each([
      ['open', ['investigating', 'resolved', 'dismissed']],
      ['investigating', ['resolved', 'dismissed', 'open']],
      ['resolved', ['open']],
      ['dismissed', ['open']],
    ] as const)(
      'offers, for an incident that is %s, the changes that make sense',
      async (status, offered) => {
        const { wrapper } = await open({ found: detail({ status }) })

        const buttons = wrapper.findAll('[data-test^="action-"]')
        expect(buttons.map((button) => button.attributes('data-test'))).toEqual(
          offered.map((one) => `action-${one}`),
        )
      },
    )

    it('changes the status when a change is chosen, with the sign-in’s security token', async () => {
      const { find, setStatus, text } = await open()
      setStatus.mockResolvedValue(detail({ status: 'investigating' }))

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(setStatus).toHaveBeenCalledWith(1, 'investigating', 'a-security-token')
      expect(text('incident-meaning')).toContain('Investigating')
      expect(text('notice')).toBe('Marked as investigating.')
      expect(find('action-resolved').exists()).toBe(true)
      expect(find('action-investigating').exists()).toBe(false)
    })

    it('says an incident that was reopened is reopened', async () => {
      const { find, setStatus, text } = await open({ found: detail({ status: 'resolved' }) })
      setStatus.mockResolvedValue(detail({ status: 'open' }))

      await find('action-open').trigger('click')
      await flushPromises()

      expect(text('notice')).toBe('Reopened.')
    })

    it('shows that the change is under way, and lets no other be started meanwhile', async () => {
      const { find, setStatus } = await open()
      setStatus.mockReturnValue(new Promise(() => {}))

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(find('action-resolved').classes()).toContain('v-btn--loading')
      expect(find('action-dismissed').attributes('disabled')).toBeDefined()
      expect(find('action-investigating').attributes('disabled')).toBeDefined()
    })

    it('says why a change was not made, and keeps what it has', async () => {
      const { find, setStatus, text } = await open()
      setStatus.mockRejectedValue(offline())

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(text('change-error')).toContain("Can't reach AresGate.")
      expect(find('notice').exists()).toBe(false)
      expect(text('incident-meaning')).toContain('Open')
      expect(find('action-resolved').attributes('disabled')).toBeUndefined()
    })

    it('forgets the failure of a change when the next is made', async () => {
      const { find, setStatus } = await open()
      setStatus.mockRejectedValueOnce(offline())
      await find('action-resolved').trigger('click')
      await flushPromises()

      setStatus.mockResolvedValue(detail({ status: 'dismissed' }))
      await find('action-dismissed').trigger('click')
      await flushPromises()

      expect(find('change-error').exists()).toBe(false)
      expect(find('notice').exists()).toBe(true)
    })

    it('lets the failure be closed', async () => {
      const { find, wrapper, setStatus } = await open()
      setStatus.mockRejectedValue(offline())
      await find('action-resolved').trigger('click')
      await flushPromises()

      await wrapper.find('[data-test="change-error"] button').trigger('click')

      expect(find('change-error').exists()).toBe(false)
    })

    it('goes to the sign-in page when the sign-in has ended', async () => {
      const { find, setStatus, pinia } = await open()
      setStatus.mockRejectedValue(new ApiError(401, 'Sign in.', 'unauthenticated'))

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(useSessionStore(pinia).expired).toBe(true)
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, text, fetchIncident } = await open({ found: offline() })

      expect(text('incident-error')).toContain("Can't reach AresGate.")
      expect(find('tiles').exists()).toBe(false)

      fetchIncident.mockResolvedValue(detail())
      await find('retry').trigger('click')
      await flushPromises()

      expect(find('incident-error').exists()).toBe(false)
      expect(find('tiles').exists()).toBe(true)
    })

    it('says an incident that is not there may have been removed, and does not offer to try again', async () => {
      const { find, text } = await open({
        found: new ApiError(404, 'No such incident.', 'not_found'),
      })

      expect(text('incident-error')).toContain('No such incident. It may have been removed.')
      expect(find('retry').exists()).toBe(false)
    })

    it('leads back to the list from the page that says so', async () => {
      const { wrapper } = await open({ found: new ApiError(404, 'No such incident.', 'not_found') })

      expect(wrapper.find('a[href="/incidents"]').exists()).toBe(true)
    })

    it('keeps what it has while a refresh fails, and says how old it is', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident } = await open()
        fetchIncident.mockRejectedValue(offline())

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(text('incident-stale')).toContain("Can't reach AresGate.")
        expect(text('incident-stale')).toMatch(/is from \d/)
        expect(find('tiles').exists()).toBe(true)

        fetchIncident.mockResolvedValue(detail())
        vi.advanceTimersByTime(30_000)
        await flushPromises()
        expect(find('incident-stale').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('says it was removed when a refresh finds it gone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident } = await open()
        fetchIncident.mockRejectedValue(new ApiError(404, 'No such incident.', 'not_found'))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(text('incident-stale')).toContain('No such incident.')
        expect(find('tiles').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe('refreshing', () => {
    it('asks again every half minute while the page is open, and shows what changed', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchIncident, text } = await open()
        expect(text('tile-signals')).toContain('3')
        fetchIncident.mockResolvedValue(detail({ signal_count: 4, signals: [signal(), signal()] }))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchIncident).toHaveBeenCalledTimes(2)
        expect(text('tile-signals')).toContain('4')
      } finally {
        vi.useRealTimers()
      }
    })

    it('says when the numbers on screen arrived', async () => {
      const { text } = await open()

      expect(text('updated')).toMatch(/^Updated \d/)
      expect(text('updated')).toContain('every 30 seconds')
    })

    it('does not let an answer that was already on its way undo a change just made', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident, setStatus } = await open()
        let settle: (value: incidentsApi.IncidentDetail) => void = () => {}
        setStatus.mockReturnValue(new Promise((resolve) => (settle = resolve)))
        await find('action-resolved').trigger('click')
        fetchIncident.mockResolvedValue(detail({ status: 'open' }))

        vi.advanceTimersByTime(30_000)
        await flushPromises()
        settle(detail({ status: 'resolved' }))
        await flushPromises()

        expect(text('incident-meaning')).toContain('Resolved')
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores an old answer that arrives after a newer one', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
        let late: (value: incidentsApi.IncidentDetail) => void = () => {}
        fetchIncident.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
        fetchIncident.mockResolvedValue(detail({ status: 'investigating' }))
        const { text } = await (async () => {
          const mounted = await mountWithPlugins(IncidentView, {
            signedIn: 'admin',
            withApp: true,
            route: '/incidents/1',
          })
          vi.advanceTimersByTime(30_000)
          await flushPromises()
          return {
            ...mounted,
            text: (id: string) => mounted.wrapper.find(`[data-test="${id}"]`).text(),
          }
        })()

        late(detail({ status: 'open' }))
        await flushPromises()

        expect(text('incident-meaning')).toContain('Investigating')
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the failure of an old request that arrives after a newer answer', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
        let fail: (reason: Error) => void = () => {}
        fetchIncident.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
        fetchIncident.mockResolvedValue(detail())
        const { wrapper } = await mountWithPlugins(IncidentView, {
          signedIn: 'admin',
          withApp: true,
          route: '/incidents/1',
        })
        vi.advanceTimersByTime(30_000)
        await flushPromises()

        fail(offline())
        await flushPromises()

        expect(wrapper.find('[data-test="incident-stale"]').exists()).toBe(false)
        expect(wrapper.find('[data-test="incident-error"]').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  it('keeps the incident it was given and does not mix it with another', async () => {
    const { text } = await open({
      found: detail({ ...incident({ id: 1, title: 'Port scan (198.51.100.7)' }) }),
    })

    expect(text('incident-meaning')).toContain('Open')
    expect(text('tile-signals')).toContain('3')
  })
})
