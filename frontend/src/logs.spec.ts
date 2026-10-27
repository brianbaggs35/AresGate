import type { LogVolume } from '@/api/logs'
import {
  COLUMNS,
  COLUMNS_KEY,
  DEFAULT_COLUMNS,
  MAX_ROWS,
  TIME_KEY,
  cursorBefore,
  endpoint,
  fieldsOf,
  jsonTokens,
  mergeEvents,
  newOnes,
  rawText,
  readColumns,
  readTimeMode,
  routeOf,
  tableRows,
  volumeBars,
  withinRange,
  writeColumns,
  writeTimeMode,
} from '@/logs'
import { logEvent } from '@/test/logs'

const at = (minutes: number) => new Date(2026, 9, 27, 8, minutes).toISOString()

describe('the order of the events', () => {
  it('puts the newest first, once each, with a later copy replacing an earlier one', () => {
    const old = logEvent({ id: 1, at: at(0) })
    const middle = logEvent({ id: 2, at: at(1) })
    const newest = logEvent({ id: 3, at: at(2), summary: 'the new one' })

    const merged = mergeEvents(
      [middle, old],
      [newest, middle, { ...old, summary: 'again' }],
      MAX_ROWS,
    )

    expect(merged.map(({ id }) => id)).toEqual([3, 2, 1])
    expect(merged[2]?.summary).toBe('again')
  })

  it('puts events of the same moment by their number, the highest first', () => {
    const merged = mergeEvents(
      [logEvent({ id: 5, at: at(0) })],
      [logEvent({ id: 9, at: at(0) })],
      MAX_ROWS,
    )

    expect(merged.map(({ id }) => id)).toEqual([9, 5])
  })

  it('keeps only so many, the newest', () => {
    const many = Array.from({ length: 6 }, (_, index) => logEvent({ id: index + 1, at: at(index) }))

    expect(mergeEvents(many.slice(0, 3), many.slice(3), 4).map(({ id }) => id)).toEqual([
      6, 5, 4, 3,
    ])
    expect(MAX_ROWS).toBeGreaterThan(100)
  })

  it('tells which events are new', () => {
    const known = logEvent({ id: 1 })
    const fresh = logEvent({ id: 2 })

    expect(newOnes([known], [fresh, known])).toEqual([fresh])
    expect(newOnes([], [])).toEqual([])
  })

  it('finds a cursor a while before an event', () => {
    expect(cursorBefore('1793000060000000.12', 60)).toBe('1793000000000000.0')
  })
})

describe('where an event came from and went', () => {
  it('writes an address with its port, an IPv6 one in brackets', () => {
    expect(endpoint('10.0.0.5', 22)).toBe('10.0.0.5:22')
    expect(endpoint('10.0.0.5', null)).toBe('10.0.0.5')
    expect(endpoint('2001:db8::1', 22)).toBe('[2001:db8::1]:22')
    expect(endpoint('2001:db8::1', null)).toBe('2001:db8::1')
    expect(endpoint(null, 53)).toBe(':53')
    expect(endpoint(null, null)).toBe('')
  })

  it('draws a line from one to the other, or shows the one there is', () => {
    expect(routeOf(logEvent())).toBe('93.184.216.34:51514 → 192.168.1.20:22')
    expect(routeOf(logEvent({ dst_address: null, dst_port: null }))).toBe('93.184.216.34:51514')
    expect(routeOf(logEvent({ src_address: null, src_port: null }))).toBe('192.168.1.20:22')
    expect(
      routeOf(logEvent({ src_address: null, src_port: null, dst_address: null, dst_port: null })),
    ).toBe('')
  })
})

describe('the volume over time', () => {
  const volume = (changes: Partial<LogVolume> = {}): LogVolume => ({
    start: at(0),
    seconds: 300,
    // Info, low, medium, high, critical in each bar.
    counts: [
      [0, 2, 0, 0, 0],
      [0, 0, 3, 1, 0],
      [0, 0, 0, 0, 0],
    ],
    ...changes,
  })

  it('has a bar for each stretch, labelled with its time', () => {
    const { categories } = volumeBars(volume(), 'en-US')

    expect(categories).toEqual(['8:00 AM', '8:05 AM', '8:10 AM'])
  })

  it('adds the day to the labels once the bars span more than one', () => {
    const { categories } = volumeBars(
      volume({ start: new Date(2026, 9, 26, 23, 55).toISOString() }),
      'en-US',
    )

    expect(categories[0]).toMatch(/Oct 26.*11:55 PM/)
    expect(categories[2]).toMatch(/Oct 27.*12:05 AM/)
  })

  it('labels bars of a day by the day', () => {
    const { categories } = volumeBars(
      volume({ start: new Date(2026, 9, 25).toISOString(), seconds: 86_400 }),
      'en-US',
    )

    expect(categories).toEqual(['Oct 25', 'Oct 26', 'Oct 27'])
  })

  it('has a series for each severity there is any of, the least serious first', () => {
    const { series } = volumeBars(volume(), 'en-US')

    expect(series.map(({ id, values }) => [id, values])).toEqual([
      ['low', [2, 0, 0]],
      ['medium', [0, 3, 0]],
      ['high', [0, 1, 0]],
    ])
    expect(series[0]?.color).toBe('var(--chart-severity-low)')
    expect(series[0]?.label).toBe('Low')
    expect(series[0]?.icon).toBeDefined()
  })

  it('says the stretch of time each bar is, to the second', () => {
    const { ranges } = volumeBars(volume({ start: '2026-10-27T08:00:00Z' }), 'en-US')

    expect(ranges[0]).toEqual({ start: '2026-10-27T08:00:00Z', end: '2026-10-27T08:05:00Z' })
    expect(ranges[2]).toEqual({ start: '2026-10-27T08:10:00Z', end: '2026-10-27T08:15:00Z' })
  })

  it('copes with a bar that has fewer counts than there are severities', () => {
    const { series } = volumeBars(volume({ counts: [[1]] }), 'en-US')

    expect(series.map(({ id, values }) => [id, values])).toEqual([['info', [1]]])
  })

  it('has nothing to draw for a volume of no bars', () => {
    const bars = volumeBars(volume({ counts: [] }), 'en-US')

    expect(bars.categories).toEqual([])
    expect(bars.series).toEqual([])
    expect(bars.ranges).toEqual([])
  })
})

describe('narrowing a search to a stretch of time', () => {
  const range = { start: '2026-10-27T08:00:00Z', end: '2026-10-27T08:05:00Z' }

  it('adds the time to a search', () => {
    expect(withinRange('kind:alert', range)).toBe(
      'kind:alert since:2026-10-27T08:00:00Z before:2026-10-27T08:05:00Z',
    )
    expect(withinRange('', range)).toBe('since:2026-10-27T08:00:00Z before:2026-10-27T08:05:00Z')
  })

  it('replaces the time it had, whichever way it was written', () => {
    expect(withinRange('since:6h kind:alert before:"2026-10-01 08:00"', range)).toBe(
      'kind:alert since:2026-10-27T08:00:00Z before:2026-10-27T08:05:00Z',
    )
    expect(withinRange('-since=today ssh', range)).toBe(
      'ssh since:2026-10-27T08:00:00Z before:2026-10-27T08:05:00Z',
    )
  })

  it('leaves alone words that only look like a time', () => {
    expect(withinRange('presince:1h text', range)).toBe(
      'presince:1h text since:2026-10-27T08:00:00Z before:2026-10-27T08:05:00Z',
    )
  })
})

describe('the columns', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('are the usual ones until another choice is made, each named', () => {
    expect(readColumns()).toEqual(DEFAULT_COLUMNS)
    for (const { label } of COLUMNS) expect(label).not.toBe('')
  })

  it('are the ones this browser remembers, in their own order, with the time and the summary', () => {
    writeColumns(['signature', 'source'])

    expect(readColumns()).toEqual(['time', 'source', 'signature', 'summary'])
    expect(JSON.parse(localStorage.getItem(COLUMNS_KEY) ?? '')).toEqual(['signature', 'source'])
  })

  it('ignore what is stored that is not a list, or not a column', () => {
    localStorage.setItem(COLUMNS_KEY, '{"a":1}')
    expect(readColumns()).toEqual(DEFAULT_COLUMNS)

    localStorage.setItem(COLUMNS_KEY, 'not json')
    expect(readColumns()).toEqual(DEFAULT_COLUMNS)

    localStorage.setItem(COLUMNS_KEY, JSON.stringify(['protocol', 'nonsense', 4]))
    expect(readColumns()).toEqual(['time', 'protocol', 'summary'])
  })

  it('remember whether time is shown as the exact time or as how long ago', () => {
    expect(readTimeMode()).toBe('exact')

    writeTimeMode('relative')
    expect(readTimeMode()).toBe('relative')
    expect(localStorage.getItem(TIME_KEY)).toBe('"relative"')

    writeTimeMode('exact')
    expect(readTimeMode()).toBe('exact')
  })

  it('still work for the visit where storage is off', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    expect(readColumns()).toEqual(DEFAULT_COLUMNS)
    expect(readTimeMode()).toBe('exact')
    expect(() => {
      writeColumns(['kind'])
      writeTimeMode('relative')
    }).not.toThrow()
  })
})

describe('the rows of the table', () => {
  const now = new Date(2026, 9, 27, 9).getTime()
  const today = logEvent({ id: 3, at: at(30) })
  const alsoToday = logEvent({ id: 2, at: at(10) })
  const yesterday = logEvent({ id: 1, at: new Date(2026, 9, 26, 23, 59).toISOString() })

  it('have a heading before the first event of each day', () => {
    const rows = tableRows([today, alsoToday, yesterday], true, now, 'en-US')

    expect(rows.map((row) => (row.type === 'day' ? row.label : row.event.id))).toEqual([
      'Today',
      3,
      2,
      'Yesterday',
      1,
    ])
  })

  it('are only the events where the days are not wanted', () => {
    const rows = tableRows([today, yesterday], false, now, 'en-US')

    expect(rows.map((row) => row.type)).toEqual(['event', 'event'])
  })

  it('are none for no events', () => {
    expect(tableRows([], true, now)).toEqual([])
  })
})

describe('the fields of an event', () => {
  const field = (id: string, event = logEvent()) =>
    fieldsOf(event, 'en-US').find((found) => found.id === id)

  it('list what is known, with what to copy where it is not what is shown', () => {
    const event = logEvent({ at: '2026-10-27T08:03:12Z', signature: 'ET SCAN Potential SSH Scan' })
    const ids = fieldsOf(event, 'en-US').map(({ id }) => id)

    expect(ids).toEqual([
      'time',
      'received',
      'severity',
      'source',
      'connection',
      'kind',
      'signature',
      'from',
      'from-port',
      'to',
      'to-port',
      'protocol',
    ])
    expect(field('time', event)?.copy).toBe('2026-10-27T08:03:12Z')
    expect(field('time', event)?.value).toMatch(/Oct 27, 2026/)
    expect(field('source')?.value).toBe('OPNsense')
    expect(field('severity')?.value).toBe('Medium')
  })

  it('leave out what the event does not say', () => {
    const event = logEvent({
      src_address: null,
      src_port: null,
      dst_address: null,
      dst_port: null,
      protocol: null,
    })

    expect(fieldsOf(event, 'en-US').map(({ id }) => id)).toEqual([
      'time',
      'received',
      'severity',
      'source',
      'connection',
      'kind',
    ])
  })

  it('give each a search for others that are alike, in the words of the search', () => {
    const event = logEvent({ signature: 'ET SCAN Potential SSH Scan' })

    expect(Object.fromEntries(fieldsOf(event, 'en-US').map(({ id, term }) => [id, term]))).toEqual({
      time: undefined,
      received: undefined,
      severity: 'severity:medium',
      source: 'source:opnsense',
      connection: 'connection:main',
      kind: 'kind:firewall',
      signature: 'signature:"ET SCAN Potential SSH Scan"',
      from: 'from:93.184.216.34',
      'from-port': 'sport:51514',
      to: 'to:192.168.1.20',
      'to-port': 'port:22',
      protocol: 'protocol:tcp',
    })
  })

  it('give none for a value that a search cannot say', () => {
    expect(field('signature', logEvent({ signature: 'say "hello"' }))?.term).toBeUndefined()
    expect(field('signature', logEvent({ signature: 'a,b' }))?.term).toBe('signature:"a,b"')
    expect(field('signature', logEvent({ signature: '' }))).toBeUndefined()
  })
})

describe("the program's own record", () => {
  it('is pretty-printed', () => {
    expect(rawText({ a: 1, b: [true, null] })).toBe(
      '{\n  "a": 1,\n  "b": [\n    true,\n    null\n  ]\n}',
    )
  })

  it('is cut into parts by what they are, with the brackets and spacing left plain', () => {
    const tokens = jsonTokens(
      rawText({ name: 'sshd', port: 22, ratio: 1.5e-7, ok: true, none: null }),
    )

    expect(
      tokens.filter(({ kind }) => kind !== 'plain').map(({ kind, text }) => [kind, text]),
    ).toEqual([
      ['key', '"name"'],
      ['string', '"sshd"'],
      ['key', '"port"'],
      ['number', '22'],
      ['key', '"ratio"'],
      ['number', '1.5e-7'],
      ['key', '"ok"'],
      ['literal', 'true'],
      ['key', '"none"'],
      ['literal', 'null'],
    ])
    expect(tokens[0]).toEqual({ kind: 'plain', text: '{\n  ' })
  })

  it('gives back all the text it was given', () => {
    const text = rawText({ nested: { list: [1, 'two', { three: 3 }], quote: 'say "hi" \\ there' } })

    expect(
      jsonTokens(text)
        .map(({ text: part }) => part)
        .join(''),
    ).toBe(text)
  })

  it('keeps whatever it does not understand as it was', () => {
    const tokens = jsonTokens('oops {"a": 1} ??')

    expect(tokens.map(({ text }) => text).join('')).toBe('oops {"a": 1} ??')
    expect(tokens.at(-1)?.kind).toBe('plain')
  })

  it('is nothing for no text', () => {
    expect(jsonTokens('')).toEqual([])
  })
})
