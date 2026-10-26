import { ApiError } from '@/api/client'
import * as storageApi from '@/api/storage'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import RetentionCard from '@/components/RetentionCard.vue'
import RetentionDialog from '@/components/RetentionDialog.vue'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const DAY = 86_400_000
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString()

const opnsense: storageApi.StorageSource = {
  source: 'opnsense',
  name: 'OPNsense',
  days: null,
  effective_days: 30,
  count: 12408,
  oldest_at: daysAgo(3),
}
const wazuh: storageApi.StorageSource = {
  source: 'wazuh',
  name: 'Wazuh',
  days: 90,
  effective_days: 90,
  count: 1,
  oldest_at: daysAgo(40),
}
const ntopng: storageApi.StorageSource = {
  source: 'ntopng',
  name: 'ntopng',
  days: null,
  effective_days: 30,
  count: 0,
  oldest_at: null,
}
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

function stored(sources = [opnsense, wazuh, ntopng], defaultDays = 30): storageApi.Storage {
  return { default_days: defaultDays, sources }
}

async function open(
  kind: storageApi.StorageKind = 'events',
  storage: storageApi.Storage | Error = stored(),
) {
  const fetchIt = vi.spyOn(storageApi, 'fetchStorage')
  if (storage instanceof Error) fetchIt.mockRejectedValue(storage)
  else fetchIt.mockResolvedValue(storage)
  const setIt = vi.spyOn(storageApi, 'setRetention')
  const mounted = await mountWithPlugins(RetentionCard, {
    signedIn: 'admin',
    withApp: true,
    props: { kind },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const rows = () => mounted.wrapper.findAll('[data-test="retention-source"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLButtonElement>(`[data-test="${selector}"]`)
  // jsdom plays no transitions, so a dialog that has closed is still there; whether it is open is
  // what the page says.
  const asking = () => mounted.wrapper.findComponent(RetentionDialog).props('modelValue')
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  const change = async (index: number) => {
    await rows()[index]?.find('[data-test="retention-change"]').trigger('click')
    await flushPromises()
  }
  const chooseDays = async (days: string) => {
    document.querySelector<HTMLInputElement>('[data-test="retention-custom"] input')!.click()
    await flushPromises()
    const field = document.querySelector<HTMLInputElement>('[data-test="retention-days"] input')!
    field.value = days
    field.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const chooseDefault = async () => {
    document.querySelector<HTMLInputElement>('[data-test="retention-default"] input')!.click()
    await flushPromises()
  }
  const save = async () => {
    inDialog('retention-save')!.click()
    await flushPromises()
    await flushPromises()
  }
  const accept = async () => {
    inDialog('confirm-accept')!.click()
    await flushPromises()
    await flushPromises()
  }
  return {
    ...mounted,
    fetchIt,
    setIt,
    find,
    rows,
    inDialog,
    asking,
    confirming,
    change,
    chooseDays,
    chooseDefault,
    save,
    accept,
  }
}

describe('RetentionCard', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(storageApi, 'fetchStorage').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(RetentionCard, {
        signedIn: 'admin',
        props: { kind: 'events' },
      })
      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
      expect(wrapper.find('[data-test="retention-list"]').exists()).toBe(false)
    })

    it('asks for its own kind of data', async () => {
      const { fetchIt } = await open('metrics')
      expect(fetchIt).toHaveBeenCalledExactlyOnceWith('metrics')
    })

    it('says what the events are and for how long they are kept unless chosen otherwise', async () => {
      const { find } = await open('events')
      expect(find('section-title').text()).toBe('Events')
      expect(find('section-description').text()).toContain('firewall log lines')
      expect(find('section-description').text()).toContain('for 30 days unless you choose')
    })

    it('says what the measurements are, and calls them readings', async () => {
      const { find, rows } = await open('metrics')
      expect(find('section-title').text()).toBe('Measurements')
      expect(find('section-description').text()).toContain('What was measured')
      expect(rows()[0]?.find('[data-test="retention-holds"]').text()).toMatch(/readings/)
    })

    it('lists each integration with how much it has stored and how long it keeps it', async () => {
      const { rows } = await open()
      const text = (index: number, selector: string) =>
        rows()[index]?.find(`[data-test="${selector}"]`).text()
      expect(rows()).toHaveLength(3)
      expect(text(0, 'retention-name')).toBe('OPNsense')
      expect(text(0, 'retention-holds')).toBe('12,408 events · the oldest 3 days ago')
      expect(text(0, 'retention-kept')).toBe('Kept for 30 days (the default)')
      expect(text(1, 'retention-name')).toBe('Wazuh')
      expect(text(1, 'retention-kept')).toBe('Kept for 90 days')
    })

    it('says event for one, and nothing is stored for an integration with none', async () => {
      const { rows } = await open()
      expect(rows()[1]?.find('[data-test="retention-holds"]').text()).toMatch(/^1 event · /)
      expect(rows()[2]?.find('[data-test="retention-holds"]').text()).toBe('No events stored')
    })

    it('charts how much each integration has stored, the most first', async () => {
      const { find } = await open('events', stored([ntopng, wazuh, opnsense]))

      const chart = find('events-chart')
      expect(chart.find('[data-test="chart-title"]').text()).toBe('Stored by integration')
      expect(chart.find('[data-test="chart-caption"]').text()).toBe(
        'How many events each one has stored now.',
      )
      expect(chart.findAll('[data-test="bar-category"]').map((name) => name.text())).toEqual([
        'OPNsense',
        'Wazuh',
        'ntopng',
      ])
      expect(chart.findAll('[data-test="bar-value"]').map((value) => value.text())).toEqual([
        '12,408',
        '1',
      ])
    })

    it('calls what a chart counts by its kind: readings for measurements', async () => {
      const { find } = await open('metrics')

      expect(find('metrics-chart').find('[data-test="chart-caption"]').text()).toBe(
        'How many readings each one has stored now.',
      )
      await find('metrics-chart').find('[data-test="chart-view"]').trigger('click')
      expect(
        find('metrics-chart')
          .findAll('thead th')
          .map((cell) => cell.text()),
      ).toEqual(['Integration', 'Measurements'])
    })

    it('has no chart while nothing is stored, and none when it could not ask', async () => {
      const nothing = await open('events', stored([ntopng]))
      expect(nothing.find('events-chart').exists()).toBe(false)
      expect(nothing.find('retention-list').exists()).toBe(true)

      const failed = await open('events', offline())
      expect(failed.find('events-chart').exists()).toBe(false)
    })

    it('says reading for one', async () => {
      const { rows } = await open('metrics')
      expect(rows()[1]?.find('[data-test="retention-holds"]').text()).toMatch(/^1 reading · /)
    })

    it('says day for one in how long it is kept', async () => {
      const { rows } = await open('events', stored([{ ...wazuh, days: 1, effective_days: 1 }]))
      expect(rows()[0]?.find('[data-test="retention-kept"]').text()).toBe('Kept for 1 day')
    })

    it('has a button for each that names what it changes', async () => {
      const { rows } = await open()
      expect(rows()[0]?.find('[data-test="retention-change"]').attributes('aria-label')).toBe(
        "Change how long OPNsense's events are kept",
      )
    })
  })

  describe('when it cannot load', () => {
    it('says so, and tries again on request', async () => {
      const { find, fetchIt, wrapper } = await open('events', offline())
      expect(find('retention-error').text()).toContain("Can't reach AresGate.")
      expect(wrapper.find('[data-test="retention-list"]').exists()).toBe(false)

      fetchIt.mockResolvedValue(stored())
      await find('events-retry').trigger('click')
      await flushPromises()

      expect(find('retention-error').exists()).toBe(false)
      expect(find('retention-list').exists()).toBe(true)
    })

    it('notes that the sign-in is over when that is the answer', async () => {
      await open('events', new ApiError(401, 'Sign in first.', 'unauthenticated'))
      expect(useSessionStore().expired).toBe(true)
    })

    it('reads again on Refresh', async () => {
      const { find, fetchIt, rows } = await open()
      fetchIt.mockResolvedValue(stored([{ ...opnsense, count: 5 }]))

      await find('events-refresh').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(rows()).toHaveLength(1)
      expect(rows()[0]?.find('[data-test="retention-holds"]').text()).toMatch(/^5 events/)
    })
  })

  describe('changing how long one is kept', () => {
    it('asks about the one chosen, showing what it keeps now', async () => {
      const { change, inDialog } = await open()

      await change(1)

      expect(inDialog('retention-title')?.textContent).toBe("How long to keep Wazuh's events")
      expect(
        document.querySelector<HTMLInputElement>('[data-test="retention-days"] input')?.value,
      ).toBe('90')
    })

    it('changes nothing when it is cancelled', async () => {
      const { change, inDialog, setIt, find, asking } = await open()
      await change(0)
      expect(asking()).toBe(true)

      inDialog('retention-cancel')!.click()
      await flushPromises()

      expect(asking()).toBe(false)
      expect(setIt).not.toHaveBeenCalled()
      expect(find('retention-notice').exists()).toBe(false)
    })

    it('keeps it for the days chosen, with the sign-in token, and says so', async () => {
      const { change, chooseDays, save, setIt, find, rows, asking } = await open()
      setIt.mockResolvedValue({ ...opnsense, days: 60, effective_days: 60 })

      await change(0)
      await chooseDays('60')
      await save()

      expect(setIt).toHaveBeenCalledExactlyOnceWith('events', 'opnsense', 60, 'a-security-token')
      expect(find('retention-notice').text()).toBe('OPNsense keeps its events for 60 days.')
      expect(rows()[0]?.find('[data-test="retention-kept"]').text()).toBe('Kept for 60 days')
      expect(asking()).toBe(false)
    })

    it('goes back to the default, and says so', async () => {
      const { change, chooseDefault, save, setIt, find, rows } = await open(
        'events',
        stored([opnsense, { ...wazuh, oldest_at: daysAgo(10) }, ntopng]),
      )
      setIt.mockResolvedValue({ ...wazuh, days: null, effective_days: 30 })

      await change(1)
      await chooseDefault()
      await save()

      expect(setIt).toHaveBeenCalledExactlyOnceWith('events', 'wazuh', null, 'a-security-token')
      expect(find('retention-notice').text()).toBe(
        'Wazuh keeps its events for 30 days (the default).',
      )
      expect(rows()[1]?.find('[data-test="retention-kept"]').text()).toBe(
        'Kept for 30 days (the default)',
      )
    })

    it('does nothing but close when the answer is what it already is', async () => {
      const { change, save, setIt, find, asking } = await open()

      await change(0)
      await save()

      expect(setIt).not.toHaveBeenCalled()
      expect(find('retention-notice').exists()).toBe(false)
      expect(asking()).toBe(false)
    })

    it('says what went wrong, and leaves the list as it was', async () => {
      const { change, chooseDays, save, setIt, find, rows, asking } = await open()
      setIt.mockRejectedValue(offline())

      await change(0)
      await chooseDays('60')
      await save()

      expect(find('retention-failure').text()).toBe("Can't reach AresGate.")
      expect(find('retention-notice').exists()).toBe(false)
      expect(rows()[0]?.find('[data-test="retention-kept"]').text()).toBe(
        'Kept for 30 days (the default)',
      )
      expect(asking()).toBe(false)
    })

    it('forgets the last result when it is asked again', async () => {
      const { change, chooseDays, save, setIt, find } = await open()
      setIt.mockResolvedValue({ ...opnsense, days: 60, effective_days: 60 })
      await change(0)
      await chooseDays('60')
      await save()
      expect(find('retention-notice').exists()).toBe(true)

      await change(2)

      expect(find('retention-notice').exists()).toBe(false)
    })

    it('keeps measurements for the days chosen too', async () => {
      const { change, chooseDays, save, setIt, find } = await open('metrics')
      setIt.mockResolvedValue({ ...opnsense, days: 7, effective_days: 7 })

      await change(0)
      await chooseDays('7')
      await save()

      expect(setIt).toHaveBeenCalledExactlyOnceWith('metrics', 'opnsense', 7, 'a-security-token')
      expect(find('retention-notice').text()).toBe('OPNsense keeps its readings for 7 days.')
    })
  })

  describe('when keeping less removes what is stored', () => {
    it('asks first, saying what goes and that it cannot be brought back', async () => {
      const { change, chooseDays, save, setIt, inDialog, asking } = await open()

      await change(0)
      await chooseDays('2')
      await save()

      expect(setIt).not.toHaveBeenCalled()
      expect(inDialog('confirm-title')?.textContent).toBe('Remove older events?')
      const message = inDialog('confirm-message')?.textContent ?? ''
      expect(message).toContain("Some of OPNsense's events are older than 2 days, back to")
      expect(message).toContain("can't be brought back")
      expect(asking()).toBe(false)
    })

    it('goes ahead when that is confirmed', async () => {
      const { change, chooseDays, save, accept, setIt, find, confirming } = await open()
      setIt.mockResolvedValue({ ...opnsense, days: 2, effective_days: 2 })
      await change(0)
      await chooseDays('2')
      await save()

      await accept()

      expect(setIt).toHaveBeenCalledExactlyOnceWith('events', 'opnsense', 2, 'a-security-token')
      expect(find('retention-notice').text()).toBe('OPNsense keeps its events for 2 days.')
      expect(confirming()).toBe(false)
    })

    it('leaves everything as it was when it is declined', async () => {
      const { change, chooseDays, save, setIt, find, inDialog } = await open()
      await change(0)
      await chooseDays('2')
      await save()

      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(setIt).not.toHaveBeenCalled()
      expect(find('retention-notice').exists()).toBe(false)
    })

    it('asks when the default would remove them, too', async () => {
      const { change, chooseDefault, save, inDialog } = await open(
        'events',
        stored([{ ...wazuh, oldest_at: daysAgo(60) }], 30),
      )

      await change(0)
      await chooseDefault()
      await save()

      expect(inDialog('confirm-message')?.textContent).toContain('older than 30 days')
    })

    it('says what went wrong if the change then fails', async () => {
      const { change, chooseDays, save, accept, setIt, find, confirming } = await open()
      setIt.mockRejectedValue(offline())
      await change(0)
      await chooseDays('2')
      await save()

      await accept()

      expect(find('retention-failure').text()).toBe("Can't reach AresGate.")
      expect(confirming()).toBe(false)
    })

    it.each([
      ['more time', '365'],
      ['as much time as the oldest has', '4'],
    ])('does not ask for %s', async (_what, days) => {
      const { change, chooseDays, save, setIt, confirming } = await open()
      setIt.mockResolvedValue({ ...opnsense, days: Number(days), effective_days: Number(days) })

      await change(0)
      await chooseDays(days)
      await save()

      expect(confirming()).toBe(false)
      expect(setIt).toHaveBeenCalledTimes(1)
    })

    it('does not ask about an integration that has nothing stored', async () => {
      const { change, chooseDays, save, setIt, confirming } = await open()
      setIt.mockResolvedValue({ ...ntopng, days: 1, effective_days: 1 })

      await change(2)
      await chooseDays('1')
      await save()

      expect(confirming()).toBe(false)
      expect(setIt).toHaveBeenCalledTimes(1)
    })
  })
})
