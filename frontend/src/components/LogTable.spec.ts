import LogTable from '@/components/LogTable.vue'
import { DEFAULT_COLUMNS, type ColumnKey } from '@/logs'
import { mountWithPlugins } from '@/test/mount'
import { logEvent } from '@/test/logs'

const NOW = new Date(2026, 9, 27, 9, 0, 0).getTime()
const at = (day: number, hour: number, minute = 0) =>
  new Date(2026, 9, day, hour, minute, 7).toISOString()

const events = [
  logEvent({ id: 3, at: at(27, 8, 58), severity: 'high', summary: 'Failed password for root' }),
  logEvent({ id: 2, at: at(27, 8, 30), source: 'wazuh', source_name: 'Wazuh', kind: 'alert' }),
  logEvent({
    id: 1,
    at: at(26, 23, 59),
    severity: 'info',
    src_address: '2001:db8::1',
    src_port: null,
    dst_address: null,
    dst_port: 53,
    protocol: null,
  }),
]

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(LogTable, {
    withApp: true,
    props: {
      events,
      columns: DEFAULT_COLUMNS,
      time: 'exact',
      selected: null,
      now: NOW,
      ...props,
    },
  })
  const rows = () => mounted.wrapper.findAll('[data-test="log-row"]')
  const cells = (row: number, column: string) =>
    rows()[row]?.find(`[data-column="${column}"]`).text()
  // The table is inside the page's app, so what it says comes from its own component.
  const emitted = () => mounted.wrapper.findComponent(LogTable).emitted('open') ?? []
  return { ...mounted, rows, cells, emitted }
}

afterEach(() => {
  window.getSelection()?.removeAllRanges()
})

describe('LogTable', () => {
  it('has a heading for each column that is shown, in a table that is named', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('caption').text()).toBe('Events, the newest first')
    expect(wrapper.findAll('th').map((heading) => heading.text())).toEqual([
      'Time',
      'Severity',
      'Source',
      'Kind',
      'From',
      'To',
      'Summary',
    ])
    expect(wrapper.find('th').attributes('scope')).toBe('col')
  })

  it('has a row for each event, with what each column says', async () => {
    const { rows, cells } = await open()

    expect(rows()).toHaveLength(3)
    expect(cells(0, 'severity')).toBe('High')
    expect(cells(0, 'source')).toBe('OPNsense')
    expect(cells(1, 'source')).toBe('Wazuh')
    expect(cells(1, 'kind')).toBe('alert')
    expect(cells(0, 'from')).toBe('93.184.216.34:51514')
    expect(cells(0, 'to')).toBe('192.168.1.20:22')
    expect(cells(2, 'from')).toBe('2001:db8::1')
    expect(cells(2, 'to')).toBe(':53')
    expect(cells(0, 'summary')).toBe('Failed password for root')
  })

  it('says how serious each is by more than its color: an icon and the word', async () => {
    const { rows } = await open()

    const severity = rows()[0]?.find('[data-column="severity"]')
    expect(severity?.find('svg').exists()).toBe(true)
    expect(severity?.text()).toBe('High')
    expect(rows()[0]?.attributes('style')).toContain('--accent: rgb(var(--v-theme-error))')
  })

  it('shows the exact time with a heading for each day, and how long ago in its tooltip', async () => {
    const { wrapper, cells, rows } = await open()

    expect(wrapper.findAll('[data-test="log-day"]').map((day) => day.text())).toEqual([
      'Today',
      'Yesterday',
    ])
    expect(cells(0, 'time')).toMatch(/8:58:07/)
    const time = rows()[0]?.find('time')
    expect(time?.attributes('datetime')).toBe(events[0]?.at)
    expect(time?.attributes('title')).toMatch(/Oct 27, 2026.*\(2 minutes ago\)/)
  })

  it('shows how long ago instead, with no headings for the days, and the exact time in its tooltip', async () => {
    const { wrapper, cells, rows } = await open({ time: 'relative' })

    expect(wrapper.findAll('[data-test="log-day"]')).toHaveLength(0)
    expect(cells(0, 'time')).toBe('2 minutes ago')
    expect(cells(1, 'time')).toBe('30 minutes ago')
    expect(rows()[1]?.find('time').attributes('title')).toMatch(/Oct 27, 2026.*8:30:07/)
  })

  it('shows the columns that are chosen, wherever they are in the row', async () => {
    const columns: ColumnKey[] = [
      'time',
      'protocol',
      'signature',
      'connection',
      'received',
      'summary',
    ]
    const { wrapper, cells } = await open({
      columns,
      events: [logEvent({ signature: 'ET SCAN Potential SSH Scan' })],
    })

    expect(wrapper.findAll('th').map((heading) => heading.text())).toEqual([
      'Time',
      'Protocol',
      'Rule',
      'Connection',
      'Received',
      'Summary',
    ])
    expect(cells(0, 'protocol')).toBe('tcp')
    expect(cells(0, 'signature')).toBe('ET SCAN Potential SSH Scan')
    expect(cells(0, 'connection')).toBe('main')
    expect(cells(0, 'received')).toMatch(/:\d\d:\d\d/)
  })

  it('has no rows for no events', async () => {
    const { rows, wrapper } = await open({ events: [] })

    expect(rows()).toHaveLength(0)
    expect(wrapper.find('thead').exists()).toBe(true)
  })

  it('marks the event that is open', async () => {
    const { rows } = await open({ selected: events[1]?.cursor })

    expect(rows().map((row) => row.classes().includes('log-table__row--on'))).toEqual([
      false,
      true,
      false,
    ])
    expect(rows()[1]?.find('button').attributes('aria-current')).toBe('true')
    expect(rows()[0]?.find('button').attributes('aria-current')).toBeUndefined()
  })

  describe('opening an event', () => {
    it('is a click anywhere on its row', async () => {
      const { rows, emitted } = await open()

      await rows()[1]?.find('[data-column="source"]').trigger('click')
      await rows()[2]?.trigger('click')

      expect(emitted()).toEqual([[events[1]], [events[2]]])
    })

    it('is Enter on its summary, which arrives as a click', async () => {
      const { rows, emitted } = await open()

      rows()[0]?.find<HTMLButtonElement>('button').element.click()

      expect(emitted()).toEqual([[events[0]]])
    })

    it('is not the end of selecting some of its text', async () => {
      const { rows, emitted } = await open()
      const cell = rows()[0]?.find('[data-column="source"]').element as Element
      window.getSelection()?.selectAllChildren(cell)

      await rows()[0]?.find('[data-column="source"]').trigger('click')

      expect(emitted()).toEqual([])
    })

    it('goes ahead where the browser has no selection to ask', async () => {
      const { rows, emitted } = await open()
      vi.spyOn(window, 'getSelection').mockReturnValue(null)

      await rows()[0]?.trigger('click')

      expect(emitted()).toHaveLength(1)
    })

    it('opens nothing for a row whose event is no longer in the list', async () => {
      const { rows, emitted } = await open()
      rows()[0]?.element.setAttribute('data-cursor', 'gone')

      await rows()[0]?.trigger('click')

      expect(emitted()).toEqual([])
    })

    it('is not a click on a heading, or a day', async () => {
      const { wrapper, emitted } = await open()

      await wrapper.find('th').trigger('click')
      await wrapper.find('[data-test="log-day"]').trigger('click')

      expect(emitted()).toEqual([])
    })
  })

  describe('with the keyboard', () => {
    const press = (
      wrapper: Awaited<ReturnType<typeof open>>['wrapper'],
      from: number,
      key: string,
    ) => {
      const buttons = wrapper.findAll<HTMLButtonElement>('.log-table__open')
      buttons[from]?.element.focus()
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      buttons[from]?.element.dispatchEvent(event)
      return event
    }

    it('moves between the summaries with the arrow keys, Home and End', async () => {
      const { wrapper } = await open()
      const active = () => document.activeElement?.textContent.trim()

      press(wrapper, 0, 'ArrowDown')
      expect(active()).toBe(events[1]?.summary)
      press(wrapper, 1, 'ArrowUp')
      expect(active()).toBe(events[0]?.summary)
      press(wrapper, 0, 'End')
      expect(active()).toBe(events[2]?.summary)
      press(wrapper, 2, 'Home')
      expect(active()).toBe(events[0]?.summary)
    })

    it('stops at the first and the last', async () => {
      const { wrapper } = await open()
      const active = () => document.activeElement?.textContent.trim()

      press(wrapper, 0, 'ArrowUp')
      expect(active()).toBe(events[0]?.summary)
      press(wrapper, 2, 'ArrowDown')
      expect(active()).toBe(events[2]?.summary)
    })

    it('leaves the other keys to the browser', async () => {
      const { wrapper } = await open()

      const event = press(wrapper, 0, 'Tab')

      expect(event.defaultPrevented).toBe(false)
    })

    it('leaves keys pressed elsewhere in the table to the browser', async () => {
      const { wrapper } = await open()
      const event = new KeyboardEvent('keydown', {
        key: 'ArrowDown',
        bubbles: true,
        cancelable: true,
      })

      wrapper.find('[data-test="log-row"] td').element.dispatchEvent(event)

      expect(event.defaultPrevented).toBe(false)
    })
  })

  it('stops listening when it has gone', async () => {
    const { wrapper, rows } = await open()
    const row = rows()[0]?.element as Element
    const body = row.parentElement as HTMLElement

    wrapper.unmount()
    body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    row.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(wrapper.emitted()).toEqual({})
  })
})
