import { ApiError } from '@/api/client'
import * as api from '@/api/logs'
import { COLUMNS_KEY, TIME_KEY, cursorBefore } from '@/logs'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { logDetail, logEvent, logEvents, logPage } from '@/test/logs'
import LogDrawer from '@/components/LogDrawer.vue'
import LogsView from '@/views/LogsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const invalid = () => new ApiError(422, 'No such field: "sevrity".', 'invalid')

/** Three events, the newest first. */
function some() {
  return logEvents(3)
}

interface Options {
  route?: string
  answer?: api.LogPage | Error
  width?: number
}

async function open({ route = '/logs', answer = logPage(some()), width }: Options = {}) {
  const fetchLogs = vi.spyOn(api, 'fetchLogs')
  if (answer instanceof Error) fetchLogs.mockRejectedValue(answer)
  else fetchLogs.mockResolvedValue(answer)
  const fetchLog = vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
  const mounted = await mountWithPlugins(LogsView, {
    signedIn: 'admin',
    withApp: true,
    route,
    // A width stays set from one test to the next, so every test says which it is.
    width: width ?? 1280,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const summaries = () =>
    mounted.wrapper
      .findAll('[data-test="log-open"], [data-test="log-card"] .log-card__summary')
      .map((row) => row.text())
  /** Does what someone does to the search, and waits for the new address of the page (which
   * takes a moment to arrive) and for the events to be asked for again. */
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchLogs, fetchLog, find, text, summaries, choose }
}

function lastQuery(fetchLogs: { mock: { calls: unknown[][] } }) {
  return fetchLogs.mock.calls.at(-1)?.[0] as api.LogQuery
}

const scrollTo = () => vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)

function scrollDown(distance: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value: distance })
  window.dispatchEvent(new Event('scroll'))
}

afterEach(() => {
  scrollDown(0)
  vi.useRealTimers()
})

describe('LogsView', () => {
  describe('the first page', () => {
    it('asks for the newest events, with the search from the address and the time zone', async () => {
      const { fetchLogs } = await open({ route: '/logs?q=kind%3Aalert' })

      expect(fetchLogs).toHaveBeenCalledTimes(1)
      expect(lastQuery(fetchLogs)).toEqual({
        q: 'kind:alert',
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        limit: 100,
      })
    })

    it('shows a skeleton until the first answer arrives', async () => {
      vi.spyOn(api, 'fetchLogs').mockReturnValue(new Promise(() => undefined))
      const { wrapper } = await mountWithPlugins(LogsView, { signedIn: 'admin' })

      expect(wrapper.find('[data-test="logs-loading"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="log-table"]').exists()).toBe(false)
    })

    it('is named, and says what it is for', async () => {
      const { text } = await open()

      expect(text('page-heading')).toBe('Logs')
      expect(text('page-description')).toContain('raw record')
    })

    it('lists the events as they were sent, in a table on a wide screen', async () => {
      const { summaries, find } = await open()

      expect(summaries()).toEqual([
        'Blocked connection number 3',
        'Blocked connection number 2',
        'Blocked connection number 1',
      ])
      expect(find('log-table').exists()).toBe(true)
      expect(find('log-cards').exists()).toBe(false)
      expect(find('log-view').exists()).toBe(true)
    })

    it('lists them as cards on a phone, without the menu for columns', async () => {
      const { summaries, find } = await open({ width: 400 })

      expect(summaries()).toHaveLength(3)
      expect(find('log-cards').exists()).toBe(true)
      expect(find('log-table').exists()).toBe(false)
      expect(find('log-view').exists()).toBe(false)
    })

    it('says how many events matched', async () => {
      const { text } = await open()

      expect(text('matched')).toBe('3 events')
    })

    it('says "event" for one, and that it is the newest when there were more', async () => {
      const one = await open({ answer: logPage([logEvent()]) })
      expect(one.text('matched')).toBe('1 event')

      const capped = logPage(some())
      const { summary } = capped
      const many = await open({
        answer: { ...capped, summary: summary && { ...summary, matched: 50_000, capped: true } },
      })
      expect(many.text('matched')).toMatch(/^The newest 50,000 events$/)
    })

    it('draws how the events are spread over time', async () => {
      const { find } = await open()

      expect(find('volume-card').exists()).toBe(true)
      expect(find('log-volume').exists()).toBe(true)
    })

    it('says when the numbers arrived, and that it asks again by itself', async () => {
      const { text } = await open()

      expect(text('updated')).toMatch(/^Updated \d/)
      expect(text('updated')).toContain('every 5 seconds')
    })

    it('says so, with a way to try again, when it can not load', async () => {
      const { find, fetchLogs } = await open({ answer: offline() })
      expect(find('logs-error').text()).toContain("Can't reach AresGate.")
      expect(find('log-table').exists()).toBe(false)

      fetchLogs.mockResolvedValue(logPage(some()))
      await find('retry').trigger('click')
      await flushPromises()

      expect(find('logs-error').exists()).toBe(false)
      expect(find('log-table').exists()).toBe(true)
    })
  })

  describe('the empty page', () => {
    it('says there are no events yet, and where to connect an integration', async () => {
      const { find } = await open({ answer: logPage([], { summary: null }) })

      expect(find('empty-title').text()).toBe('No events yet')
      expect(find('empty-integrations').attributes('href')).toBe('/integrations')
      expect(find('log-table').exists()).toBe(false)
      expect(find('volume-card').exists()).toBe(false)
    })

    it('says nothing matches a search, and clears it on request', async () => {
      const { find, router, fetchLogs, choose } = await open({
        route: '/logs?q=kind%3Anothing',
        answer: logPage([], { summary: null }),
      })
      expect(find('empty-title').text()).toBe('Nothing matches')

      fetchLogs.mockResolvedValue(logPage(some()))
      await choose(() => find('empty-clear').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
      expect(find('log-table').exists()).toBe(true)
    })
  })

  describe('searching', () => {
    it('asks again with the search, and puts it in the address of the page', async () => {
      const { wrapper, router, fetchLogs, choose } = await open()

      await choose(async () => {
        const box = wrapper.find<HTMLInputElement>('[data-test="search"] input')
        await box.setValue('severity>=high')
        await box.trigger('keydown.enter')
      })

      expect(router.currentRoute.value.query).toEqual({ q: 'severity>=high' })
      expect(lastQuery(fetchLogs).q).toBe('severity>=high')
    })

    it('shows how the search was understood, as chips', async () => {
      const answer = logPage(some(), {
        terms: [{ field: 'kind', label: 'Kind: alert', negated: false, start: 0, end: 10 }],
      })
      const { wrapper } = await open({ route: '/logs?q=kind%3Aalert', answer })

      expect(wrapper.findAll('[data-test="search-term"]').map((chip) => chip.text())).toEqual([
        'Kind: alert',
      ])
    })

    it('has the choices for severity, integration and kind, which add to the search', async () => {
      const { find, router, fetchLogs, choose } = await open()

      expect(find('facet-severity:medium').text()).toContain('3')
      expect(find('facet-source:opnsense').text()).toContain('3')
      expect(find('facet-kind:firewall').text()).toContain('3')

      await choose(() => find('facet-kind:firewall').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ q: 'kind:firewall' })
      expect(lastQuery(fetchLogs).q).toBe('kind:firewall')

      await choose(() => find('facet-severity:medium').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ q: 'kind:firewall severity:medium' })

      await choose(() => find('facet-kind:firewall').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ q: 'severity:medium' })
    })

    it('narrows to a stretch of time when a bar of the chart is picked', async () => {
      const { wrapper, router, choose } = await open({ route: '/logs?q=kind%3Aalert+since%3A6h' })

      await choose(() => wrapper.findAll('[data-test="bar-slot"]')[0]?.trigger('click'))

      expect(router.currentRoute.value.query.q).toMatch(
        /^kind:alert since:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ before:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/,
      )
    })

    it('says why a search can not be understood, and keeps the events from the one before', async () => {
      const { find, text, fetchLogs, summaries, choose, wrapper } = await open()
      fetchLogs.mockRejectedValue(invalid())

      await choose(async () => {
        const box = wrapper.find<HTMLInputElement>('[data-test="search"] input')
        await box.setValue('sevrity:high')
        await box.trigger('keydown.enter')
      })

      expect(find('search').text()).toContain('No such field')
      expect(find('search-stale').exists()).toBe(true)
      expect(summaries()).toHaveLength(3)
      expect(find('more').exists()).toBe(false)
      expect(text('matched')).toBe('3 events')
    })

    it('says so instead of the events when the first search can not be understood', async () => {
      const { find } = await open({ route: '/logs?q=sevrity%3Ahigh', answer: invalid() })

      expect(find('search').text()).toContain('No such field')
      expect(find('empty-title').text()).toBe("That search can't be understood")
      expect(find('logs-error').exists()).toBe(false)
      expect(find('search-stale').exists()).toBe(false)
    })

    it('takes a search that arrives from outside, as a link from the drawer does', async () => {
      const { router, fetchLogs, choose } = await open()

      await choose(() => router.push({ name: 'logs', query: { q: 'address:10.0.0.5' } }))

      expect(lastQuery(fetchLogs).q).toBe('address:10.0.0.5')
    })
  })

  describe('older events', () => {
    it('are asked for from the last one on screen, and go below it', async () => {
      const first = logEvents(3, 6)
      const { find, fetchLogs, summaries } = await open({
        answer: logPage(first, { more: true }),
      })
      expect(find('more').text()).toContain('Showing 3 of 3')

      fetchLogs.mockResolvedValue(logPage(logEvents(3, 3, 3), { more: false, summary: null }))
      await find('show-older').trigger('click')
      await flushPromises()

      expect(lastQuery(fetchLogs)).toEqual(
        expect.objectContaining({ before: first[2]?.cursor, summary: false, limit: 100 }),
      )
      expect(summaries()).toHaveLength(6)
      expect(find('more').exists()).toBe(false)
    })

    it('say how many more the search found than are on screen', async () => {
      const found = logPage(logEvents(3, 6), { more: true })
      const { text } = await open({
        answer: { ...found, summary: found.summary && { ...found.summary, matched: 1200 } },
      })
      expect(text('more')).toContain('Showing 3 of 1,200.')

      const capped = await open({
        answer: {
          ...found,
          summary: found.summary && { ...found.summary, matched: 50_000, capped: true },
        },
      })
      expect(capped.text('more')).toContain('Showing 3 of 50,000+.')
    })

    it('say so when they could not be asked for, and are asked for again', async () => {
      const { find, fetchLogs } = await open({ answer: logPage(logEvents(3, 6), { more: true }) })
      fetchLogs.mockRejectedValue(offline())

      await find('show-older').trigger('click')
      await flushPromises()
      expect(find('logs-stale').exists()).toBe(true)

      fetchLogs.mockResolvedValue(logPage(logEvents(3, 3, 3), { more: false, summary: null }))
      await find('show-older').trigger('click')
      await flushPromises()
      expect(find('logs-stale').exists()).toBe(false)
    })

    it('are not asked for when there is nothing on screen to go on from', async () => {
      const { find, fetchLogs } = await open({ answer: logPage([], { more: true, summary: null }) })

      expect(find('show-older').exists()).toBe(true)
      fetchLogs.mockClear()
      await find('show-older').trigger('click')

      expect(fetchLogs).not.toHaveBeenCalled()
    })

    it('are not blamed when the search changed while they were on their way', async () => {
      const { find, fetchLogs, choose } = await open({
        answer: logPage(logEvents(3, 6), { more: true }),
      })
      let fail: (reason: Error) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await find('show-older').trigger('click')

      fetchLogs.mockResolvedValue(logPage([logEvent({ id: 90 })]))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      fail(offline())
      await flushPromises()

      expect(find('logs-stale').exists()).toBe(false)
    })

    it('are dropped when the search changed while they were on their way', async () => {
      const { find, fetchLogs, summaries, choose } = await open({
        answer: logPage(logEvents(3, 6), { more: true }),
      })
      let late: (page: api.LogPage) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await find('show-older').trigger('click')

      fetchLogs.mockResolvedValue(logPage([logEvent({ id: 90, summary: 'The new search' })]))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      late(logPage(logEvents(3, 3, 3)))
      await flushPromises()

      expect(summaries()).toEqual(['The new search'])
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchLogs, choose } = await open()

      await choose(() => find('refresh').trigger('click'))

      expect(fetchLogs).toHaveBeenCalledTimes(2)
    })

    it('ignores the answer to a search that is no longer the one made', async () => {
      const { find, summaries, fetchLogs, choose } = await open()
      let late: (page: api.LogPage) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      fetchLogs.mockResolvedValueOnce(logPage([logEvent({ id: 80, summary: 'The other one' })]))
      await choose(() => find('facet-source:opnsense').trigger('click'))

      late(logPage([logEvent({ id: 81, summary: 'Too late' })]))
      await flushPromises()

      expect(summaries()).toEqual(['The other one'])
    })

    it('ignores the failure of a search that is no longer the one made', async () => {
      const { find, fetchLogs, choose } = await open()
      let fail: (reason: Error) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      await choose(() => find('facet-source:opnsense').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('logs-stale').exists()).toBe(false)
      expect(find('logs-error').exists()).toBe(false)
    })
  })

  describe('the view menu', () => {
    it('remembers which columns the table has', async () => {
      const { wrapper, find } = await open()
      await find('log-view').trigger('click')
      await flushPromises()

      document.querySelector<HTMLInputElement>('[data-test="column-protocol"] input')?.click()
      await flushPromises()

      expect(wrapper.findAll('th').map((heading) => heading.text())).toContain('Protocol')
      expect(JSON.parse(localStorage.getItem(COLUMNS_KEY) ?? '[]')).toContain('protocol')
    })

    it('remembers whether the time is the exact time or how long ago', async () => {
      const { wrapper, find } = await open()
      await find('log-view').trigger('click')
      await flushPromises()

      document.querySelector<HTMLInputElement>('[data-test="time-relative"] input')?.click()
      await flushPromises()

      expect(wrapper.find('[data-column="time"]').text()).toMatch(/ago|just now/)
      expect(localStorage.getItem(TIME_KEY)).toBe('"relative"')
    })

    it('starts from what this browser remembers', async () => {
      localStorage.setItem(COLUMNS_KEY, JSON.stringify(['kind']))
      localStorage.setItem(TIME_KEY, '"relative"')
      const { wrapper } = await open()

      expect(wrapper.findAll('th').map((heading) => heading.text())).toEqual([
        'Time',
        'Kind',
        'Summary',
      ])
    })
  })

  describe('exporting', () => {
    it('offers the events that the search finds as CSV or JSON, to be saved as a file', async () => {
      const { find } = await open({ route: '/logs?q=kind%3Aalert' })
      await find('export').trigger('click')
      await flushPromises()

      const link = (name: string) =>
        document.querySelector<HTMLAnchorElement>(`[data-test="${name}"]`)
      const zone = encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)
      expect(link('export-csv')?.getAttribute('href')).toBe(
        `/api/logs/export?format=csv&q=kind%3Aalert&tz=${zone}`,
      )
      expect(link('export-json')?.getAttribute('href')).toContain('format=json')
      expect(link('export-json')?.hasAttribute('download')).toBe(true)
    })
  })

  describe('following along', () => {
    const arrives = (...events: api.LogEvent[]) => logPage(events, { more: false, summary: null })

    it('asks every few seconds for what is new, from a little before the newest event', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const events = some()
      const { fetchLogs } = await open({ answer: logPage(events) })
      fetchLogs.mockClear()
      fetchLogs.mockResolvedValue(arrives())

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(fetchLogs).toHaveBeenCalledTimes(1)
      expect(lastQuery(fetchLogs)).toEqual(
        expect.objectContaining({
          after: cursorBefore(events[0]?.cursor ?? '', 60),
          summary: false,
          limit: 100,
        }),
      )
    })

    it('puts what arrives above the events, once each, in order', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const events = some()
      const newest = logEvent({
        id: 4,
        at: new Date(Date.now() - 1000).toISOString(),
        summary: 'Just now',
      })
      const { fetchLogs, summaries, text } = await open({ answer: logPage(events) })
      // The overlap brings back the events it already has.
      fetchLogs.mockResolvedValue(arrives(newest, ...events.slice(0, 2)))

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(summaries()).toEqual([
        'Just now',
        'Blocked connection number 3',
        'Blocked connection number 2',
        'Blocked connection number 1',
      ])
      expect(text('updated')).toMatch(/^Updated/)
    })

    it('goes on asking while a burst is bigger than a page', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, summaries } = await open()
      const second = logEvent({
        id: 12,
        at: new Date(Date.now() - 2000).toISOString(),
        summary: 'B',
      })
      const third = logEvent({
        id: 13,
        at: new Date(Date.now() - 1000).toISOString(),
        summary: 'C',
      })
      fetchLogs.mockClear()
      fetchLogs
        .mockResolvedValueOnce(logPage([second], { more: true, summary: null }))
        .mockResolvedValueOnce(logPage([third], { more: false, summary: null }))

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(fetchLogs).toHaveBeenCalledTimes(2)
      expect(lastQuery(fetchLogs).after).toBe(second.cursor)
      expect(summaries().slice(0, 2)).toEqual(['C', 'B'])
    })

    it('starts from the newest page when nothing was on screen', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, summaries } = await open({ answer: logPage([], { summary: null }) })
      fetchLogs.mockClear()
      // `more` here says there are older events, which is not a reason to ask again.
      fetchLogs.mockResolvedValue(logPage(some(), { more: true, summary: null }))

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(fetchLogs).toHaveBeenCalledTimes(1)
      expect(lastQuery(fetchLogs).after).toBeUndefined()
      expect(summaries()).toHaveLength(3)
    })

    it('waits above the fold while the page is scrolled down, and says how many', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, summaries } = await open()
      scrollDown(900)
      fetchLogs.mockResolvedValue(
        arrives(
          logEvent({ id: 5, at: new Date(Date.now() - 500).toISOString(), summary: 'Newer' }),
          logEvent({ id: 4, at: new Date(Date.now() - 900).toISOString(), summary: 'New' }),
        ),
      )

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(summaries()).toHaveLength(3)
      expect(find('new-events').text()).toBe('2 new events')
    })

    it('says "1 new event" for one, and puts them in with a click that goes back up', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const jump = scrollTo()
      const { fetchLogs, find, summaries } = await open()
      scrollDown(900)
      fetchLogs.mockResolvedValue(
        arrives(
          logEvent({ id: 5, at: new Date(Date.now() - 500).toISOString(), summary: 'Newer' }),
        ),
      )
      vi.advanceTimersByTime(5000)
      await flushPromises()
      expect(find('new-events').text()).toBe('1 new event')

      await find('new-events').trigger('click')

      expect(summaries()[0]).toBe('Newer')
      expect(find('new-events').exists()).toBe(false)
      expect(jump).toHaveBeenCalledWith({ top: 0, behavior: 'auto' })
    })

    it('goes up smoothly unless motion is reduced', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const jump = scrollTo()
      const { fetchLogs, find } = await open()
      scrollDown(900)
      fetchLogs.mockResolvedValue(
        arrives(logEvent({ id: 5, at: new Date(Date.now() - 500).toISOString() })),
      )
      vi.advanceTimersByTime(5000)
      await flushPromises()
      vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList)

      await find('new-events').trigger('click')

      expect(jump).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
    })

    it('puts them in by itself once the page is scrolled back to the top', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, summaries } = await open()
      scrollDown(900)
      fetchLogs.mockResolvedValue(
        arrives(
          logEvent({ id: 5, at: new Date(Date.now() - 500).toISOString(), summary: 'Newer' }),
        ),
      )
      vi.advanceTimersByTime(5000)
      await flushPromises()

      scrollDown(20)
      await flushPromises()

      expect(summaries()[0]).toBe('Newer')
      expect(find('new-events').exists()).toBe(false)
    })

    it('stops asking when it is paused, and asks at once when it is turned back on', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, text } = await open()
      expect(find('live').attributes('aria-pressed')).toBe('true')
      fetchLogs.mockClear()
      fetchLogs.mockResolvedValue(arrives())

      await find('live').trigger('click')
      expect(find('live').attributes('aria-pressed')).toBe('false')
      expect(text('updated')).toMatch(/^Paused at/)
      vi.advanceTimersByTime(60_000)
      await flushPromises()
      expect(fetchLogs).not.toHaveBeenCalled()

      await find('live').trigger('click')
      await flushPromises()
      expect(fetchLogs).toHaveBeenCalledTimes(1)
    })

    it('asks how the search is spread now and then, leaving the events alone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, text, summaries } = await open()
      fetchLogs.mockClear()
      fetchLogs.mockImplementation((query) =>
        Promise.resolve(
          query?.limit === 1 ? logPage(logEvents(5)) : logPage([], { summary: null }),
        ),
      )

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(fetchLogs.mock.calls.filter(([query]) => query?.limit === 1)).toHaveLength(1)
      expect(text('matched')).toBe('5 events')
      expect(summaries()).toHaveLength(3)
    })

    it('keeps going when how the search is spread could not be asked for', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, text } = await open()
      fetchLogs.mockRejectedValue(offline())

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(text('matched')).toBe('3 events')
      expect(find('log-table').exists()).toBe(true)
    })

    it('does not ask for a summary while paused or when the search is wrong', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find } = await open()
      await find('live').trigger('click')
      fetchLogs.mockClear()

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(fetchLogs).not.toHaveBeenCalled()
    })

    it('says so when it can not reach AresGate, and is quiet again when it can', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find } = await open()
      fetchLogs.mockRejectedValue(offline())

      vi.advanceTimersByTime(5000)
      await flushPromises()
      expect(find('logs-stale').text()).toContain("Can't reach AresGate.")
      expect(find('log-table').exists()).toBe(true)

      fetchLogs.mockResolvedValue(arrives())
      vi.advanceTimersByTime(5000)
      await flushPromises()
      expect(find('logs-stale').exists()).toBe(false)
    })

    it('does not ask again while it is still waiting for the answer', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs } = await open()
      fetchLogs.mockClear()
      fetchLogs.mockReturnValue(new Promise(() => undefined))

      vi.advanceTimersByTime(5000)
      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(fetchLogs).toHaveBeenCalledTimes(1)
    })

    it('drops what arrives for a search that is no longer the one made', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, summaries, choose } = await open()
      let late: (page: api.LogPage) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      vi.advanceTimersByTime(5000)
      await flushPromises()

      fetchLogs.mockResolvedValue(logPage([logEvent({ id: 70, summary: 'The new search' })]))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      late(arrives(logEvent({ id: 71, summary: 'Too late' })))
      await flushPromises()

      expect(summaries()).toEqual(['The new search'])
    })

    it('does not blame a search for the failure of a tail for another', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, choose } = await open()
      let fail: (reason: Error) => void = () => undefined
      fetchLogs.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      vi.advanceTimersByTime(5000)
      await flushPromises()

      fetchLogs.mockResolvedValue(logPage([logEvent({ id: 70 })]))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      fail(offline())
      await flushPromises()

      expect(find('logs-stale').exists()).toBe(false)
    })

    it('drops how a search was spread when it is no longer the one made', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs, find, text, choose } = await open()
      let late: (page: api.LogPage) => void = () => undefined
      fetchLogs.mockImplementation((query) =>
        query?.limit === 1
          ? new Promise((resolve) => (late = resolve))
          : Promise.resolve(logPage([], { summary: null })),
      )
      vi.advanceTimersByTime(30_000)
      await flushPromises()

      fetchLogs.mockResolvedValue(logPage([logEvent({ id: 70 })]))
      await choose(() => find('facet-kind:firewall').trigger('click'))
      late(logPage(logEvents(9)))
      await flushPromises()

      expect(text('matched')).toBe('1 event')
    })

    it('does not mix what arrives into a failed load', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      const { fetchLogs } = await open({ answer: offline() })
      fetchLogs.mockClear()

      vi.advanceTimersByTime(5000)
      await flushPromises()

      expect(fetchLogs).not.toHaveBeenCalled()
    })
  })

  describe('the drawer', () => {
    it('opens the event that was clicked, and marks it in the list', async () => {
      const { wrapper, fetchLog, find } = await open()

      await wrapper.findAll('[data-test="log-row"]')[1]?.trigger('click')
      await flushPromises()

      const events = some()
      expect(fetchLog).toHaveBeenCalledWith(events[1]?.cursor)
      expect(document.querySelector('[data-test="drawer-title"]')?.textContent.trim()).toBe(
        'Blocked connection number 2',
      )
      expect(wrapper.findAll('[data-test="log-row"]')[1]?.classes()).toContain('log-table__row--on')
      expect(find('log-table').exists()).toBe(true)
    })

    it('opens an event from a card on a phone', async () => {
      const { wrapper } = await open({ width: 400 })

      await wrapper.findAll('[data-test="log-card"]')[0]?.trigger('click')
      await flushPromises()

      expect(document.querySelector('[data-test="log-drawer"]')).not.toBeNull()
    })

    const inDrawer = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
    const title = () => inDrawer('drawer-title')?.textContent.trim()

    it('goes to the next older and the next newer event', async () => {
      const { wrapper } = await open()
      await wrapper.findAll('[data-test="log-row"]')[1]?.trigger('click')
      await flushPromises()

      inDrawer('drawer-older')?.click()
      await flushPromises()
      expect(title()).toBe('Blocked connection number 1')
      expect(inDrawer('drawer-older')?.hasAttribute('disabled')).toBe(true)

      inDrawer('drawer-newer')?.click()
      inDrawer('drawer-newer')?.click()
      await flushPromises()
      expect(title()).toBe('Blocked connection number 3')
      expect(inDrawer('drawer-newer')?.hasAttribute('disabled')).toBe(true)
    })

    it('asks for older events when it is at the last one on screen', async () => {
      const { wrapper, fetchLogs } = await open({
        answer: logPage(logEvents(3, 6), { more: true }),
      })
      await wrapper.findAll('[data-test="log-row"]')[2]?.trigger('click')
      await flushPromises()
      expect(inDrawer('drawer-older')?.hasAttribute('disabled')).toBe(false)

      fetchLogs.mockResolvedValue(logPage(logEvents(3, 3, 3), { more: false, summary: null }))
      inDrawer('drawer-older')?.click()
      await flushPromises()

      expect(title()).toBe('Blocked connection number 3')
      expect(wrapper.findAll('[data-test="log-row"]')).toHaveLength(6)
    })

    it('stays where it is when the older events could not be asked for', async () => {
      const { wrapper, fetchLogs } = await open({
        answer: logPage(logEvents(3, 6), { more: true }),
      })
      await wrapper.findAll('[data-test="log-row"]')[2]?.trigger('click')
      await flushPromises()

      fetchLogs.mockRejectedValue(offline())
      inDrawer('drawer-older')?.click()
      await flushPromises()

      expect(title()).toBe('Blocked connection number 4')
    })

    it('narrows the search to events like one of its fields, and closes', async () => {
      const jump = scrollTo()
      const { wrapper, router, fetchLogs, choose } = await open()
      await wrapper.findAll('[data-test="log-row"]')[0]?.trigger('click')
      await flushPromises()

      await choose(() => inDrawer('find-to-port')?.click())

      expect(router.currentRoute.value.query).toEqual({ q: 'port:22' })
      expect(lastQuery(fetchLogs).q).toBe('port:22')
      expect(wrapper.findComponent(LogDrawer).props('modelValue')).toBe(false)
      expect(jump).toHaveBeenCalledWith({ top: 0 })
    })

    it('does not add a term that the search already has', async () => {
      scrollTo()
      const { wrapper, router, choose } = await open({ route: '/logs?q=port%3A22' })
      await wrapper.findAll('[data-test="log-row"]')[0]?.trigger('click')
      await flushPromises()

      await choose(() => inDrawer('find-to-port')?.click())

      expect(router.currentRoute.value.query).toEqual({ q: 'port:22' })
    })

    it('is put away by its own button', async () => {
      const { wrapper } = await open()
      await wrapper.findAll('[data-test="log-row"]')[0]?.trigger('click')
      await flushPromises()

      inDrawer('drawer-close')?.click()
      await flushPromises()

      expect(wrapper.findComponent(LogDrawer).props('modelValue')).toBe(false)
      expect(wrapper.find('.log-table__row--on').exists()).toBe(false)
    })

    it('is closed when the search changes', async () => {
      const { wrapper, find, choose } = await open()
      await wrapper.findAll('[data-test="log-row"]')[0]?.trigger('click')
      await flushPromises()
      expect(inDrawer('log-drawer')).not.toBeNull()

      await choose(() => find('facet-kind:firewall').trigger('click'))

      expect(wrapper.findComponent(LogDrawer).props('modelValue')).toBe(false)
    })
  })

  describe('and the slash key', () => {
    const slash = (target: EventTarget = window, init: KeyboardEventInit = {}) => {
      const event = new KeyboardEvent('keydown', {
        key: '/',
        bubbles: true,
        cancelable: true,
        ...init,
      })
      target.dispatchEvent(event)
      return event
    }

    it('goes to the search box from anywhere on the page', async () => {
      const { wrapper } = await open()
      const box = wrapper.find<HTMLInputElement>('[data-test="search"] input').element

      expect(slash().defaultPrevented).toBe(true)

      expect(document.activeElement).toBe(box)
    })

    it('leaves the key alone in a field, and with another key held', async () => {
      const { wrapper } = await open()
      const box = wrapper.find<HTMLInputElement>('[data-test="search"] input').element

      expect(slash(box).defaultPrevented).toBe(false)
      expect(slash(window, { ctrlKey: true }).defaultPrevented).toBe(false)
      expect(slash(window, { metaKey: true }).defaultPrevented).toBe(false)
      expect(slash(window, { altKey: true }).defaultPrevented).toBe(false)
      expect(slash(window, { key: 'k' }).defaultPrevented).toBe(false)
    })

    it('is left alone while an event is open in the sheet', async () => {
      const { wrapper } = await open()
      await wrapper.findAll('[data-test="log-row"]')[0]?.trigger('click')
      await flushPromises()

      expect(slash().defaultPrevented).toBe(false)
    })

    it('is let go of when the page is left', async () => {
      const { wrapper } = await open()
      wrapper.unmount()

      expect(slash().defaultPrevented).toBe(false)
    })
  })
})
