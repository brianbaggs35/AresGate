import type { VueWrapper } from '@vue/test-utils'
import { VBtnToggle, VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import * as verdictsApi from '@/api/verdicts'
import { useSessionStore } from '@/stores/session'
import { incident, page } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'
import IncidentsView from '@/views/IncidentsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

/** Three incidents: one open, one being looked at, one over. */
function some() {
  return page(
    [
      incident({ id: 3, title: 'Port scan (198.51.100.7)', severity: 'critical' }),
      incident({ id: 2, title: 'Brute force on ssh (203.0.113.9)', status: 'investigating' }),
    ],
    { counts: { open: 1, investigating: 1, resolved: 1, dismissed: 0 }, total: 2 },
  )
}

interface Options {
  route?: string
  answer?: incidentsApi.IncidentPage | Error
}

async function open({ route = '/incidents', answer = some() }: Options = {}) {
  const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
  if (answer instanceof Error) fetchIncidents.mockRejectedValue(answer)
  else fetchIncidents.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(IncidentsView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const titles = () =>
    mounted.wrapper.findAll('[data-test="incident-title"]').map((title) => title.text())
  /** Does what someone does to the filters, and waits for the new address of the page (which
   * takes a moment to arrive) and for the list to be asked for again. */
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchIncidents, find, text, titles, choose }
}

function last(fetchIncidents: { mock: { calls: unknown[][] } }) {
  return fetchIncidents.mock.calls.at(-1)?.[0] as incidentsApi.IncidentQuery
}

describe('IncidentsView', () => {
  it('asks for the incidents that are open or being looked at', async () => {
    const { fetchIncidents } = await open()

    expect(fetchIncidents).toHaveBeenCalledTimes(1)
    expect(last(fetchIncidents)).toEqual({
      statuses: ['open', 'investigating'],
      verdicts: ['none', 'threat'],
      minConfidence: 0,
      limit: 25,
    })
  })

  it('shows a skeleton until the first answer arrives', async () => {
    vi.spyOn(incidentsApi, 'fetchIncidents').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IncidentsView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="incidents-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="incident-list"]').exists()).toBe(false)
  })

  it('lists them as they were sent, most urgent first', async () => {
    const { titles, find } = await open()

    expect(titles()).toEqual(['Port scan (198.51.100.7)', 'Brute force on ssh (203.0.113.9)'])
    expect(find('incidents-empty').exists()).toBe(false)
  })

  it('counts the incidents in each view, from every incident there is', async () => {
    const { text } = await open()

    expect(text('count-active')).toBe('2')
    expect(text('count-open')).toBe('1')
    expect(text('count-investigating')).toBe('1')
    expect(text('count-resolved')).toBe('1')
    expect(text('count-dismissed')).toBe('0')
    expect(text('count-all')).toBe('3')
  })

  it('says when the numbers on screen arrived', async () => {
    const { text } = await open()

    expect(text('updated')).toMatch(/^Updated \d/)
    expect(text('updated')).toContain('every 30 seconds')
  })

  describe('the views', () => {
    it('start from the active ones, with nothing in the address of the page', async () => {
      const { find, router } = await open()

      expect(find('view-active').classes()).toContain('v-btn--active')
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('ask for the others, and say so in the address, so a link brings them back', async () => {
      const { find, router, fetchIncidents, choose } = await open()

      await choose(() => find('view-resolved').trigger('click'))

      expect(last(fetchIncidents).statuses).toEqual(['resolved'])
      expect(router.currentRoute.value.query).toEqual({ view: 'resolved' })
      expect(find('view-resolved').classes()).toContain('v-btn--active')
    })

    it('ask for all of them with no status', async () => {
      const { find, fetchIncidents, choose } = await open()

      await choose(() => find('view-all').trigger('click'))

      expect(last(fetchIncidents).statuses).toEqual([])
    })

    it('go back to the first when the first is chosen again', async () => {
      const { find, router, choose } = await open({ route: '/incidents?view=dismissed' })

      await choose(() => find('view-active').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('stay as they are when none is chosen', async () => {
      const { wrapper, fetchIncidents, choose } = await open({ route: '/incidents?view=open' })

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', undefined)
      })

      expect(fetchIncidents).toHaveBeenCalledTimes(1)
    })

    it('come from the address of the page', async () => {
      const { find, fetchIncidents } = await open({ route: '/incidents?view=investigating' })

      expect(last(fetchIncidents).statuses).toEqual(['investigating'])
      expect(find('view-investigating').classes()).toContain('v-btn--active')
    })

    it('start again from the top, dropping what was listed for the others', async () => {
      const { find, fetchIncidents, titles, choose } = await open()
      fetchIncidents.mockResolvedValue(
        page([incident({ id: 9, title: 'Old news (192.0.2.4)', status: 'resolved' })]),
      )

      await choose(() => find('view-resolved').trigger('click'))

      expect(titles()).toEqual(['Old news (192.0.2.4)'])
    })
  })

  describe('the filters', () => {
    /** Chooses from the select that is at this place on the page. */
    const pick = (wrapper: VueWrapper, at: number, value: unknown) =>
      wrapper.findAllComponents(VSelect)[at]?.vm.$emit('update:modelValue', value)

    it('narrow the list to the serious ones', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await choose(() => pick(wrapper, 0, 'high'))

      expect(last(fetchIncidents).minSeverity).toBe('high')
      expect(router.currentRoute.value.query).toEqual({ severity: 'high' })
    })

    it('narrow it to the incidents AresGate is sure of', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await choose(() => pick(wrapper, 1, 65))

      expect(last(fetchIncidents).minConfidence).toBe(65)
      expect(router.currentRoute.value.query).toEqual({ confidence: '65' })
    })

    it('come from the address of the page, and ignore what is not a choice', async () => {
      const { fetchIncidents, find, wrapper } = await open({
        route: '/incidents?severity=high&confidence=35&view=nonsense',
      })

      expect(last(fetchIncidents)).toMatchObject({
        statuses: ['open', 'investigating'],
        minSeverity: 'high',
        minConfidence: 35,
      })
      expect(find('clear-filters').exists()).toBe(true)
      expect(wrapper.findAllComponents(VSelect)[0]?.props('modelValue')).toBe('high')
    })

    it('ignore a severity or a confidence that is not one of the choices', async () => {
      const { fetchIncidents, find } = await open({
        route: '/incidents?severity=catastrophic&confidence=12&address[]=x',
      })

      expect(last(fetchIncidents)).toEqual({
        statuses: ['open', 'investigating'],
        verdicts: ['none', 'threat'],
        minConfidence: 0,
        limit: 25,
      })
      expect(find('clear-filters').exists()).toBe(false)
    })

    it('look for a whole address once it is typed, and not before', async () => {
      const { wrapper, router, fetchIncidents, find, choose } = await open()
      const address = wrapper.find('[data-test="filter-address"] input')

      await choose(() => address.setValue('93.184'))
      expect(fetchIncidents).toHaveBeenCalledTimes(1)
      expect(find('filter-address').text()).toContain('Type a whole IP address to look for it.')

      await choose(() => address.setValue(' 93.184.216.34 '))
      expect(last(fetchIncidents).address).toBe('93.184.216.34')
      expect(router.currentRoute.value.query).toEqual({ address: '93.184.216.34' })
      expect(find('filter-address').text()).not.toContain('Type a whole')
    })

    it('stop looking for an address when it is cleared', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open({
        route: '/incidents?address=93.184.216.34',
      })
      expect(last(fetchIncidents).address).toBe('93.184.216.34')

      await choose(() =>
        wrapper.find('[data-test="filter-address"] [aria-label="Clear Address"]').trigger('click'),
      )

      expect(last(fetchIncidents).address).toBeUndefined()
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('start with the address that is in the address of the page', async () => {
      const { wrapper } = await open({ route: '/incidents?address=2001:db8::1' })

      expect(
        wrapper.find<HTMLInputElement>('[data-test="filter-address"] input').element.value,
      ).toBe('2001:db8::1')
    })

    it('are all dropped by the button for it, but not the view', async () => {
      const { find, router, fetchIncidents, wrapper, choose } = await open({
        route: '/incidents?view=resolved&severity=high&confidence=65&address=93.184.216.34',
      })

      await choose(() => find('clear-filters').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({ view: 'resolved' })
      expect(last(fetchIncidents)).toEqual({
        statuses: ['resolved'],
        verdicts: ['none', 'threat'],
        minConfidence: 0,
        limit: 25,
      })
      expect(
        wrapper.find<HTMLInputElement>('[data-test="filter-address"] input').element.value,
      ).toBe('')
      expect(find('clear-filters').exists()).toBe(false)
    })
  })

  describe('the incidents your verdicts quiet', () => {
    const withQuieted = (count: number) => ({ answer: page(some().items, { quieted: count }) })

    it('are left out of the list, with no switch to show them when there are none', async () => {
      const { find } = await open()

      expect(find('filter-quieted').exists()).toBe(false)
    })

    it('are offered by a switch that says how many there are', async () => {
      const { text } = await open(withQuieted(4))

      expect(text('filter-quieted')).toBe('Show 4 quieted by your verdicts')
    })

    it('are listed once the switch is on, and say so in the address of the page', async () => {
      const { find, router, fetchIncidents, choose } = await open(withQuieted(4))

      await choose(() => find('filter-quieted').find('input').setValue(true))

      expect(router.currentRoute.value.query).toEqual({ quieted: '1' })
      expect(last(fetchIncidents)).toEqual({
        statuses: ['open', 'investigating'],
        minConfidence: 0,
        limit: 25,
      })
    })

    it('are left out again once it is switched off', async () => {
      const { find, router, fetchIncidents, choose } = await open({
        route: '/incidents?quieted=1',
        ...withQuieted(4),
      })
      expect(find('filter-quieted').find<HTMLInputElement>('input').element.checked).toBe(true)

      await choose(() => find('filter-quieted').find('input').setValue(false))

      expect(router.currentRoute.value.query).toEqual({})
      expect(last(fetchIncidents).verdicts).toEqual(['none', 'threat'])
    })

    it('count as a filter, which the button drops', async () => {
      const { find, router, choose } = await open({
        route: '/incidents?quieted=1',
        ...withQuieted(4),
      })

      await choose(() => find('clear-filters').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('have no button to clear filters while nothing else is on', async () => {
      const { find } = await open(withQuieted(4))

      expect(find('clear-filters').exists()).toBe(false)
    })
  })

  describe('when there are no incidents to show', () => {
    const none = (counts = { open: 0, investigating: 0, resolved: 0, dismissed: 0 }) =>
      page([], { counts, total: 0 })

    it('says none have been made yet, and where the alerts come from', async () => {
      const { text, find } = await open({ answer: none() })

      expect(text('incidents-empty')).toContain('No incidents yet')
      expect(find('empty-integrations').attributes('href')).toBe('/integrations')
      expect(find('incident-list').exists()).toBe(false)
      expect(find('more').exists()).toBe(false)
    })

    it('says nothing needs anyone when the rest are over, and offers them', async () => {
      const { text, find, router, choose } = await open({
        answer: none({ open: 0, investigating: 0, resolved: 2, dismissed: 1 }),
      })

      expect(text('incidents-empty')).toContain('Nothing needs you')
      expect(text('incidents-empty')).toContain('3 in all')
      await choose(() => find('empty-all').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ view: 'all' })
    })

    it('says every incident is one you quieted, and offers them', async () => {
      const { text, find, router, choose } = await open({
        answer: page([], {
          counts: { open: 0, investigating: 0, resolved: 0, dismissed: 0 },
          total: 0,
          quieted: 2,
        }),
      })

      expect(text('incidents-empty')).toContain('Nothing needs you')
      expect(text('incidents-empty')).toContain(
        'Every incident is one you called not suspicious or low priority. 2 are hidden.',
      )
      await choose(() => find('empty-quieted').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ quieted: '1' })
    })

    it('says so in the singular for the one', async () => {
      const { text } = await open({
        answer: page([], {
          counts: { open: 0, investigating: 0, resolved: 0, dismissed: 0 },
          total: 0,
          quieted: 1,
        }),
      })

      expect(text('incidents-empty')).toContain('1 is hidden.')
    })

    it('says no incident has the status asked for', async () => {
      const { text } = await open({
        route: '/incidents?view=dismissed',
        answer: none({ open: 1, investigating: 0, resolved: 0, dismissed: 0 }),
      })

      expect(text('incidents-empty')).toContain('None here')
      expect(text('incidents-empty')).toContain('No incident has this status. 1 in all.')
    })

    it('says nothing matches the filters, and drops them', async () => {
      const { text, find, router, choose } = await open({
        route: '/incidents?severity=critical',
        answer: none({ open: 1, investigating: 0, resolved: 0, dismissed: 0 }),
      })

      expect(text('incidents-empty')).toContain('Nothing matches')
      await choose(() => find('empty-clear').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({})
    })
  })

  describe('when there are more than one page of them', () => {
    const many = (from: number, count: number, total: number) =>
      page(
        Array.from({ length: count }, (_, index) =>
          incident({ id: from - index, title: `Incident ${from - index}` }),
        ),
        { total, counts: { open: total, investigating: 0, resolved: 0, dismissed: 0 } },
      )

    it('says how many are shown and offers the next page', async () => {
      const { text } = await open({ answer: many(100, 25, 60) })

      expect(text('more')).toContain('Showing 25 of 60.')
      expect(text('show-more')).toBe('Show 25 more')
    })

    it('adds the next page after the first, from where the first ended', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open({
        answer: many(100, 25, 60),
      })
      fetchIncidents.mockResolvedValue(many(75, 25, 60))

      await choose(() => find('show-more').trigger('click'))

      expect(last(fetchIncidents)).toMatchObject({ offset: 25, limit: 25 })
      expect(titles()).toHaveLength(50)
      expect(titles()[25]).toBe('Incident 75')
      expect(text('more')).toContain('Showing 50 of 60.')
      expect(text('show-more')).toBe('Show 10 more')
    })

    it('stops offering more when all are shown', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 30) })
      fetchIncidents.mockResolvedValue(many(75, 5, 30))

      await choose(() => find('show-more').trigger('click'))

      expect(find('more').exists()).toBe(false)
    })

    it('keeps as many as are on screen when it asks again, so nothing disappears', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      fetchIncidents.mockResolvedValue(many(75, 25, 60))
      await choose(() => find('show-more').trigger('click'))

      fetchIncidents.mockResolvedValue(many(100, 50, 60))
      await choose(() => find('refresh').trigger('click'))

      expect(last(fetchIncidents).limit).toBe(50)
      expect(last(fetchIncidents).offset).toBeUndefined()
    })

    it('says so when the next page cannot be had, and keeps the first', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open({
        answer: many(100, 25, 60),
      })
      fetchIncidents.mockRejectedValue(offline())

      await choose(() => find('show-more').trigger('click'))

      expect(text('incidents-stale')).toContain("Can't reach AresGate.")
      expect(titles()).toHaveLength(25)
    })

    it('drops the answer for a page that is no longer wanted', async () => {
      const { find, titles, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      let late: (value: incidentsApi.IncidentPage) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await choose(() => find('show-more').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(many(100, 25, 60))
      await choose(() => find('refresh').trigger('click'))

      late(many(75, 25, 60))
      await flushPromises()

      expect(titles()).toHaveLength(25)
    })

    it('drops the failure of a page that is no longer wanted', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      let fail: (reason: Error) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('show-more').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(many(100, 25, 60))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('incidents-stale').exists()).toBe(false)
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchIncidents, choose } = await open()

      await choose(() => find('refresh').trigger('click'))

      expect(fetchIncidents).toHaveBeenCalledTimes(2)
    })

    it('asks again every half minute while the page is open, leaving what is on screen alone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchIncidents, find } = await open()
        fetchIncidents.mockReturnValue(new Promise(() => {}))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchIncidents).toHaveBeenCalledTimes(2)
        expect(find('incident-list').exists()).toBe(true)
        expect(find('incidents-loading').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the answer to a choice that is no longer the one made', async () => {
      const { find, titles, fetchIncidents, choose } = await open()
      let late: (value: incidentsApi.IncidentPage) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await choose(() => find('view-resolved').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(page([incident({ id: 8, title: 'The other one' })]))
      await choose(() => find('view-all').trigger('click'))

      late(page([incident({ id: 9, title: 'Too late' })]))
      await flushPromises()

      expect(titles()).toEqual(['The other one'])
    })

    it('ignores the failure of a choice that is no longer the one made', async () => {
      const { find, fetchIncidents, choose } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('view-resolved').trigger('click'))
      await choose(() => find('view-all').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('incidents-stale').exists()).toBe(false)
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, text, fetchIncidents, choose } = await open({ answer: offline() })

      expect(text('incidents-error')).toContain("Can't reach AresGate.")
      expect(find('incident-list').exists()).toBe(false)

      fetchIncidents.mockResolvedValue(some())
      await choose(() => find('retry').trigger('click'))

      expect(find('incidents-error').exists()).toBe(false)
      expect(find('incident-list').exists()).toBe(true)
    })

    it('keeps what it has while a refresh fails, and says how old it is', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open()
      fetchIncidents.mockRejectedValue(offline())

      await choose(() => find('refresh').trigger('click'))

      expect(text('incidents-stale')).toContain("Can't reach AresGate.")
      expect(text('incidents-stale')).toMatch(/is from \d/)
      expect(titles()).toHaveLength(2)

      fetchIncidents.mockResolvedValue(some())
      await choose(() => find('refresh').trigger('click'))
      expect(find('incidents-stale').exists()).toBe(false)
    })

    it('goes to the sign-in page when the sign-in has ended', async () => {
      const { pinia } = await open({
        answer: new ApiError(401, 'Sign in.', 'unauthenticated') as unknown as Error,
      })

      expect(useSessionStore(pinia).expired).toBe(true)
    })
  })
  describe('saying what you think of an incident from the list', () => {
    /** What the page says in its notice at the bottom, which is outside the page itself. */
    const notice = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

    async function judge(kept = given()) {
      const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(kept)
      const change = vi.spyOn(verdictsApi, 'changeVerdict').mockResolvedValue(kept)
      const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
      const opened = await open()
      const press = async (kind: string) => {
        await opened.wrapper.find(`[data-test="quick-${kind}"]`).trigger('click')
        await flushPromises()
        await flushPromises()
      }
      const undo = async () => {
        notice('undo')?.click()
        await flushPromises()
        await flushPromises()
      }
      return { ...opened, give, change, remove, press, undo }
    }

    it('says what was remembered and asks for the list again, since it can leave it', async () => {
      const { press, fetchIncidents } = await judge()

      await press('not_suspicious')

      expect(notice('judged-text')?.textContent).toBe(
        'Remembered: 93.184.216.34 is not suspicious.',
      )
      expect(fetchIncidents).toHaveBeenCalledTimes(2)
    })

    it('takes back a new verdict, and asks for the list again', async () => {
      const { press, undo, remove, change, fetchIncidents } = await judge(given({ id: 7 }))
      await press('not_suspicious')

      await undo()

      expect(remove).toHaveBeenCalledWith(7, 'a-security-token')
      expect(change).not.toHaveBeenCalled()
      expect(notice('judged-text')?.textContent).toBe('Taken back.')
      expect(notice('undo')).toBeNull()
      expect(fetchIncidents).toHaveBeenCalledTimes(3)
    })
  })
})
