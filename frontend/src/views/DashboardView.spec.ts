import { ApiError } from '@/api/client'
import * as collectorsApi from '@/api/collectors'
import * as dashboardApi from '@/api/dashboard'
import * as incidentsApi from '@/api/incidents'
import * as verdictsApi from '@/api/verdicts'
import { useSessionStore } from '@/stores/session'
import { collector, report } from '@/test/collectors'
import { alert, dashboard, incidentMark } from '@/test/dashboard'
import { incident, page } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'
import TrafficCard from '@/components/TrafficCard.vue'
import DashboardView from '@/views/DashboardView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

/** A dashboard where something happened: nine alerts, four of them serious. */
function busy() {
  const base = dashboard()
  const none = base.alerts.by_severity.info
  const row = (counts: Record<number, number>) => none.map((_, index) => counts[index] ?? 0)
  return dashboard({
    alerts: {
      total: 9,
      previous: 6,
      highest: 'critical',
      by_severity: {
        info: row({}),
        low: row({ 3: 3 }),
        medium: row({ 5: 2 }),
        high: row({ 20: 3 }),
        critical: row({ 22: 1 }),
      },
    },
    recent_alerts: [
      alert({ id: 2, severity: 'critical', summary: 'Beacon to a known command server' }),
      alert({ id: 1, severity: 'low', summary: 'Port scan', source_name: 'OPNsense' }),
    ],
    blocked: {
      total: 1_250,
      previous: 1_000,
      per_bucket: base.blocked.per_bucket.map((_, index) => (index === 4 ? 1_250 : 0)),
      top_sources: [
        { address: '203.0.113.9', count: 900 },
        { address: '198.51.100.7', count: 350 },
      ],
    },
    traffic: [
      {
        interface: 'igc0',
        received: base.window.traffic_buckets.map(() => 8_000_000),
        sent: base.window.traffic_buckets.map(() => 2_000_000),
      },
    ],
    devices: { total: 14, new: 2 },
  })
}

interface Mocks {
  dashboard?: dashboardApi.Dashboard | Error
  collectors?: collectorsApi.CollectorsReport | Error
  /** The incidents that need a decision. None, unless given. */
  incidents?: incidentsApi.IncidentPage | Error
}

function mocks({
  dashboard: shown = busy(),
  collectors = report([collector()]),
  incidents = page([]),
}: Mocks = {}) {
  const fetchDashboard = vi.spyOn(dashboardApi, 'fetchDashboard')
  if (shown instanceof Error) fetchDashboard.mockRejectedValue(shown)
  else fetchDashboard.mockResolvedValue(shown)
  const fetchCollectors = vi.spyOn(collectorsApi, 'fetchCollectors')
  if (collectors instanceof Error) fetchCollectors.mockRejectedValue(collectors)
  else fetchCollectors.mockResolvedValue(collectors)
  const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
  if (incidents instanceof Error) fetchIncidents.mockRejectedValue(incidents)
  else fetchIncidents.mockResolvedValue(incidents)
  return { fetchDashboard, fetchCollectors, fetchIncidents }
}

async function open(options: Mocks = {}) {
  const fetches = mocks(options)
  const mounted = await mountWithPlugins(DashboardView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, ...fetches, find, text }
}

describe('DashboardView', () => {
  it('asks for the last 24 hours and for how the collectors are doing', async () => {
    const { fetchDashboard, fetchCollectors } = await open()
    expect(fetchDashboard).toHaveBeenCalledWith('24h')
    expect(fetchCollectors).toHaveBeenCalledTimes(1)
  })

  it('shows a skeleton until the first answer arrives', async () => {
    mocks()
    vi.spyOn(dashboardApi, 'fetchDashboard').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(DashboardView, { signedIn: 'admin' })
    expect(wrapper.find('[data-test="dashboard-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="posture"]').exists()).toBe(false)
  })

  describe('the banner', () => {
    it('asks for attention when there is a serious alert', async () => {
      const { find, text } = await open()
      expect(find('posture').attributes('data-state')).toBe('attention')
      expect(text('posture-title')).toBe('Needs your attention')
      expect(text('posture-detail')).toContain('4 serious alerts in the last 24 hours')
      expect(find('posture-action').exists()).toBe(false)
    })

    it('is quiet when nothing happened and the collectors work', async () => {
      const { find, text } = await open({ dashboard: dashboard() })
      expect(find('posture').attributes('data-state')).toBe('calm')
      expect(text('posture-detail')).toBe('No alerts in the last 24 hours.')
    })

    it('asks for something to be connected when no collector is running', async () => {
      const { find, text } = await open({ dashboard: dashboard(), collectors: report([]) })
      expect(find('posture').attributes('data-state')).toBe('setup')
      expect(find('posture-action').attributes('href')).toBe('/integrations')
      expect(text('tile-collection')).toContain('None')
      expect(find('tile-collection').attributes('href')).toBe('/integrations')
    })

    it('sends someone to the status page when collectors are failing', async () => {
      const { find, text } = await open({
        collectors: report([collector({ state: 'problem' }), collector({ state: 'ok' })]),
      })
      expect(text('posture-detail')).toContain('1 collector is not working')
      expect(find('posture-action').attributes('href')).toBe('/status')
      expect(text('tile-collection')).toContain('1 failing')
      expect(text('tile-collection')).toContain('2 collectors')
      expect(find('tile-collection').attributes('href')).toBe('/status')
    })
  })

  describe('the tiles', () => {
    it('count the alerts and compare them with the time before', async () => {
      const { text } = await open()
      expect(text('tile-alerts')).toContain('Alerts')
      expect(text('tile-alerts')).toContain('9')
      expect(text('tile-alerts')).toContain('In the last 24 hours')
      expect(text('tile-alerts')).toContain('50% more than the day before')
    })

    it('count the blocked connections without calling more of them bad', async () => {
      const { find, text } = await open()
      expect(text('tile-blocked')).toContain('Blocked connections')
      expect(text('tile-blocked')).toContain('1,250')
      expect(text('tile-blocked')).toContain('25% more than the day before')
      expect(find('tile-blocked').find('[data-test="stat-delta"]').classes()).not.toContain(
        'text-error',
      )
    })

    it('count the new devices out of all that are known', async () => {
      const { text } = await open()
      expect(text('tile-devices')).toContain('New devices')
      expect(text('tile-devices')).toContain('2')
      expect(text('tile-devices')).toContain('14 known, first seen in the last 24 hours')
    })

    it('say all is well with the collectors', async () => {
      const { text } = await open()
      expect(text('tile-collection')).toContain('Working')
      expect(text('tile-collection')).toContain('1 collector')
    })

    it.each([
      ['no alerts at all', dashboard(), 'text-success'],
      [
        'a serious alert',
        dashboard({ alerts: { ...dashboard().alerts, total: 1, highest: 'high' } }),
        'text-error',
      ],
      [
        'a medium alert',
        dashboard({ alerts: { ...dashboard().alerts, total: 1, highest: 'medium' } }),
        'text-warning',
      ],
      [
        'only a low alert',
        dashboard({ alerts: { ...dashboard().alerts, total: 1, highest: 'low' } }),
        'text-primary',
      ],
    ])('color the alerts by the worst there were: %s', async (_name, shown, color) => {
      const { find } = await open({ dashboard: shown })
      expect(find('tile-alerts').find('.v-icon').classes()).toContain(color)
    })
  })

  describe('the lane of what needs you', () => {
    const waiting = () =>
      page(
        [
          incident({ id: 3, title: 'Port scan (198.51.100.7)', severity: 'critical' }),
          incident({ id: 2, title: 'Brute force on ssh (203.0.113.9)' }),
        ],
        { total: 5 },
      )

    it('asks for the three open incidents that are most serious and surest', async () => {
      const { fetchIncidents } = await open()

      expect(fetchIncidents).toHaveBeenCalledWith({
        statuses: ['open', 'investigating'],
        minConfidence: 0,
        verdicts: ['none', 'threat'],
        limit: 3,
        order: 'priority',
      })
    })

    it('shows a card for each, under the banner, and says how many there are in all', async () => {
      const { find, text, wrapper } = await open({ incidents: waiting() })

      expect(wrapper.findAll('[data-test="incident-title"]').map((title) => title.text())).toEqual([
        'Port scan (198.51.100.7)',
        'Brute force on ssh (203.0.113.9)',
      ])
      expect(text('needs-you-description')).toContain('5 open incidents')
      expect(text('needs-you-all')).toBe('See all 5')
      expect(find('posture').element.compareDocumentPosition(find('needs-you').element)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      )
    })

    it('is left out when nothing needs a decision', async () => {
      const { find } = await open()

      expect(find('needs-you').exists()).toBe(false)
    })

    it('is left out, and the rest of the page is not, when the incidents cannot be read', async () => {
      const { find } = await open({ incidents: offline() })

      expect(find('needs-you').exists()).toBe(false)
      expect(find('dashboard-error').exists()).toBe(false)
      expect(find('posture').exists()).toBe(true)
    })

    it('keeps what it has when a refresh cannot read the incidents', async () => {
      const { find, fetchIncidents } = await open({ incidents: waiting() })
      fetchIncidents.mockRejectedValue(offline())

      await find('refresh').trigger('click')
      await flushPromises()

      expect(find('needs-you').exists()).toBe(true)
      expect(find('dashboard-stale').exists()).toBe(false)
    })

    describe('saying what you think of one', () => {
      /** What the page says in its notice at the bottom, which is outside the page itself. */
      const notice = (selector: string) =>
        document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

      async function judge() {
        const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(given({ id: 7 }))
        const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
        const opened = await open({ incidents: waiting() })
        const press = async () => {
          await opened.wrapper.find('[data-test="quick-not_suspicious"]').trigger('click')
          await flushPromises()
          await flushPromises()
        }
        return { ...opened, give, remove, press }
      }

      it('says what was remembered, and asks again, since the incident can leave the lane', async () => {
        const { press, find, fetchDashboard, fetchIncidents } = await judge()
        fetchIncidents.mockResolvedValue(page([incident({ id: 2 })], { total: 1 }))

        await press()

        expect(notice('judged-text')?.textContent).toBe(
          'Remembered: 93.184.216.34 is not suspicious.',
        )
        expect(fetchDashboard).toHaveBeenCalledTimes(2)
        expect(fetchIncidents).toHaveBeenCalledTimes(2)
        expect(find('needs-you-description').text()).toContain('1 open incident,')
      })

      it('goes when the last one has been judged', async () => {
        const { press, find, fetchIncidents } = await judge()
        fetchIncidents.mockResolvedValue(page([]))

        await press()

        expect(find('needs-you').exists()).toBe(false)
      })

      it('asks again when the verdict is taken back, since the incident is back', async () => {
        const { press, remove, fetchDashboard } = await judge()
        await press()

        notice('undo')?.click()
        await flushPromises()
        await flushPromises()

        expect(remove).toHaveBeenCalledWith(7, 'a-security-token')
        expect(fetchDashboard).toHaveBeenCalledTimes(3)
      })
    })
  })

  describe('the charts', () => {
    it('chart the traffic of the busiest interface', async () => {
      const { text } = await open()
      expect(text('traffic-card')).toContain('Network traffic')
      expect(text('traffic-card')).toContain('igc0')
    })

    it('leave the buckets still to come off the traffic, so the lines reach the edge', async () => {
      const base = dashboard({}, '24h', Date.now() + 3_600_000)
      const received = base.window.traffic_buckets.map(() => 8_000_000)
      const { wrapper } = await open({
        dashboard: { ...base, traffic: [{ interface: 'igc0', received, sent: received }] },
      })
      const card = wrapper.findComponent(TrafficCard)
      const times = card.props('times')
      expect(times.length).toBeLessThan(96)
      expect(times.length).toBeGreaterThanOrEqual(92)
      expect(card.props('traffic')[0]?.received).toHaveLength(times.length)
      expect(card.props('traffic')[0]?.sent).toHaveLength(times.length)
      expect(times.every((time) => time <= Date.now())).toBe(true)
    })

    it('flag the incidents that began in the window on the traffic', async () => {
      const { wrapper } = await open({
        dashboard: dashboard({
          marks: [incidentMark(), incidentMark({ id: 2, severity: 'critical', confidence: 90 })],
        }),
      })
      const marks = wrapper.findComponent(TrafficCard).props('marks')
      expect(marks?.map(({ id }) => id)).toEqual(['incident-1', 'incident-2'])
      expect(marks?.[1]?.label).toBe('Critical incident: Brute force on ssh (93.184.216.34)')
    })

    it('flag nothing when no incident began in the window', async () => {
      const { wrapper } = await open()
      expect(wrapper.findComponent(TrafficCard).props('marks')).toEqual([])
    })

    it('say so when there is no traffic yet', async () => {
      const { text } = await open({ dashboard: dashboard() })
      expect(text('traffic-card')).toContain('No traffic recorded yet')
    })

    it('stack the alerts by severity, with only the severities there were', async () => {
      const { wrapper, text } = await open()
      expect(text('alerts-card')).toContain('Alerts by severity')
      const labels = wrapper.findAll('[data-test="alerts-card"] [data-test="chart-legend-label"]')
      expect(labels.map((label) => label.text())).toEqual(['Low', 'Medium', 'High', 'Critical'])
    })

    it('say so when there were no alerts', async () => {
      const { text } = await open({ dashboard: dashboard() })
      expect(text('alerts-card')).toContain('No alerts')
      expect(text('alerts-card')).toContain('Nothing was reported in the last 24 hours.')
    })

    it('rank the addresses that were blocked most', async () => {
      const { text } = await open()
      expect(text('sources-card')).toContain('Most blocked addresses')
      expect(text('sources-card')).toContain('203.0.113.9')
      expect(text('sources-card')).toContain('198.51.100.7')
    })

    it('say so when nothing was blocked', async () => {
      const { text } = await open({ dashboard: dashboard() })
      expect(text('sources-card')).toContain('Nothing was blocked')
    })
  })

  describe('the latest alerts', () => {
    it('lists them', async () => {
      const { wrapper, text } = await open()
      expect(text('latest-alerts-card')).toContain('Latest alerts')
      const summaries = wrapper.findAll('[data-test="alert-summary"]').map((item) => item.text())
      expect(summaries).toEqual(['Beacon to a known command server', 'Port scan'])
    })

    it('say so when there are none', async () => {
      const { find, text } = await open({ dashboard: dashboard() })
      expect(find('recent-alerts').exists()).toBe(false)
      expect(text('latest-alerts-card')).toContain('No alerts')
    })
  })

  describe('the time range', () => {
    it('shows the last week when asked, and says so everywhere', async () => {
      const { find, text, fetchDashboard, wrapper } = await open()
      fetchDashboard.mockResolvedValue({ ...busy(), ...dashboard({}, '7d') })
      await find('range-7d').trigger('click')
      await flushPromises()

      expect(fetchDashboard).toHaveBeenLastCalledWith('7d')
      expect(text('tile-alerts')).toContain('In the last 7 days')
      expect(text('tile-alerts')).not.toContain('day before')
      expect(wrapper.find('[data-test="alerts-chart"]').exists()).toBe(true)
    })

    it('goes back to the day', async () => {
      const { find, fetchDashboard } = await open()
      await find('range-7d').trigger('click')
      await flushPromises()
      await find('range-24h').trigger('click')
      await flushPromises()
      expect(fetchDashboard).toHaveBeenLastCalledWith('24h')
    })

    it('dims the charts while the other range loads, and not before', async () => {
      const { find, wrapper, fetchDashboard } = await open()
      expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(false)
      fetchDashboard.mockReturnValue(new Promise(() => {}))
      await find('range-7d').trigger('click')
      await flushPromises()
      expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(true)
    })

    it('ignores the answer to a range that is no longer the one asked for', async () => {
      const { find, text, fetchDashboard } = await open()
      let late: (value: dashboardApi.Dashboard) => void = () => {}
      fetchDashboard.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await find('range-7d').trigger('click')
      fetchDashboard.mockResolvedValueOnce(dashboard({}, '24h'))
      await find('range-24h').trigger('click')
      await flushPromises()
      late(dashboard({}, '7d'))
      await flushPromises()
      expect(text('tile-alerts')).toContain('In the last 24 hours')
    })

    it('ignores the failure of a range that is no longer the one asked for', async () => {
      const { find, wrapper, fetchDashboard } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchDashboard.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await find('range-7d').trigger('click')
      await find('range-24h').trigger('click')
      await flushPromises()
      fail(offline())
      await flushPromises()
      expect(wrapper.find('[data-test="dashboard-stale"]').exists()).toBe(false)
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchDashboard } = await open()
      await find('refresh').trigger('click')
      await flushPromises()
      expect(fetchDashboard).toHaveBeenCalledTimes(2)
    })

    it('asks again every half minute while the page is open, without dimming the charts', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchDashboard, wrapper } = await open()
        fetchDashboard.mockReturnValue(new Promise(() => {}))
        vi.advanceTimersByTime(30_000)
        await flushPromises()
        expect(fetchDashboard).toHaveBeenCalledTimes(2)
        expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('says when the numbers on screen arrived', async () => {
      const { text } = await open()
      expect(text('updated')).toMatch(/^Updated \d/)
      expect(text('updated')).toContain('every 30 seconds')
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, text, fetchDashboard } = await open({ dashboard: offline() })
      expect(text('dashboard-error')).toContain("Can't reach AresGate.")
      expect(find('posture').exists()).toBe(false)

      fetchDashboard.mockResolvedValue(busy())
      await find('retry').trigger('click')
      await flushPromises()
      expect(find('dashboard-error').exists()).toBe(false)
      expect(find('posture').exists()).toBe(true)
    })

    it('says so when only how the collectors are doing is missing', async () => {
      const { text } = await open({ collectors: offline() })
      expect(text('dashboard-error')).toContain("Can't reach AresGate.")
    })

    it('keeps what it has while a refresh fails, and says how old it is', async () => {
      const { find, text, fetchDashboard } = await open()
      fetchDashboard.mockRejectedValue(offline())
      await find('refresh').trigger('click')
      await flushPromises()
      expect(text('dashboard-stale')).toContain("Can't reach AresGate.")
      expect(text('dashboard-stale')).toMatch(/is from \d/)
      expect(find('posture').exists()).toBe(true)

      fetchDashboard.mockResolvedValue(busy())
      await find('refresh').trigger('click')
      await flushPromises()
      expect(find('dashboard-stale').exists()).toBe(false)
    })

    it('goes to the sign-in page when the sign-in has ended', async () => {
      const { pinia } = await open({ dashboard: new ApiError(401, 'Sign in.', 'unauthenticated') })
      expect(useSessionStore(pinia).expired).toBe(true)
    })
  })
})
