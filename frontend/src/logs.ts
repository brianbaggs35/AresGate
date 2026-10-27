/**
 * The logs page from the side of the person reading it: which events are kept on screen and in
 * what order, how the volume over time becomes bars, which columns the table has, and how one
 * event is laid out in the drawer. What an event is, and what a search means, is the API's.
 */
import type { LogEvent, LogVolume } from '@/api/logs'
import type { BarSeries } from '@/charts/BarChart.vue'
import { severityColor } from '@/charts/palette'
import { formatDay, formatTimestamp } from '@/format'
import { SEVERITIES, SEVERITY } from '@/severity'

/** How many events the page asks for at a time. */
export const PAGE_SIZE = 100
/** The most events kept on screen. A page that is live and left open drops the oldest ones. */
export const MAX_ROWS = 1000
/** How often a live page asks for what is new, and how often it asks how the search is spread. */
export const TAIL_SECONDS = 5
export const SUMMARY_SECONDS = 30
/** A live page asks for events from this long before the newest it has: they are in the order
 * of when they happened, and an integration can report one a little late. */
export const TAIL_OVERLAP_SECONDS = 60
/** The most times in a row a live page asks for more when a burst was bigger than a page. */
export const TAIL_ROUNDS = 5

// ---------------------------------------------------------------------------------------------
// Order

interface Position {
  micros: number
  id: number
}

/** Where an event is in the order, from its cursor (`<microseconds>.<id>`). */
function positionOf(cursor: string): Position {
  const [micros = '0', id = '0'] = cursor.split('.')
  return { micros: Number(micros), id: Number(id) }
}

/** A cursor for the moment `seconds` before the event that has this one. */
export function cursorBefore(cursor: string, seconds: number): string {
  return `${(positionOf(cursor).micros - seconds * 1_000_000).toString()}.0`
}

/** For sorting: the newest first. */
function newestFirst(a: LogEvent, b: LogEvent): number {
  const left = positionOf(a.cursor)
  const right = positionOf(b.cursor)
  return right.micros - left.micros || right.id - left.id
}

/** What is on screen with what came in added, once each and the newest first, at most `max`. */
export function mergeEvents(
  shown: readonly LogEvent[],
  incoming: readonly LogEvent[],
  max: number,
): LogEvent[] {
  const byId = new Map<number, LogEvent>()
  for (const event of [...shown, ...incoming]) byId.set(event.id, event)
  return [...byId.values()].sort(newestFirst).slice(0, max)
}

/** The events of `incoming` that `shown` does not have. */
export function newOnes(shown: readonly LogEvent[], incoming: readonly LogEvent[]): LogEvent[] {
  const known = new Set(shown.map(({ id }) => id))
  return incoming.filter(({ id }) => !known.has(id))
}

// ---------------------------------------------------------------------------------------------
// Words for an event

/** An address and its port, the way they are written: `10.0.0.5:22`, `[2001:db8::1]:22`. */
export function endpoint(address: string | null, port: number | null): string {
  if (!address) return port === null ? '' : `:${port.toString()}`
  if (port === null) return address
  return address.includes(':') ? `[${address}]:${port.toString()}` : `${address}:${port.toString()}`
}

/** Where an event came from and where it went, such as `203.0.113.7 → 192.168.1.20:22`; one end
 * alone where the event names only one. */
export function routeOf(event: LogEvent): string {
  const from = endpoint(event.src_address, event.src_port)
  const to = endpoint(event.dst_address, event.dst_port)
  if (from && to) return `${from} → ${to}`
  return from || to
}

// ---------------------------------------------------------------------------------------------
// Volume over time

export interface VolumeBars {
  /** The label of each bar, for its place on the axis and in the table. */
  categories: string[]
  /** One series for each severity there is any of, the most serious on top. */
  series: BarSeries[]
  /** The stretch of time each bar is: `start` up to `end`, as a search can say it. */
  ranges: { start: string; end: string }[]
}

const seconds = (ms: number) => new Date(ms).toISOString().replace('.000Z', 'Z')

function barLabel(start: number, width: number, days: boolean, locale?: string): string {
  const options: Intl.DateTimeFormatOptions =
    width >= 86_400
      ? { month: 'short', day: 'numeric' }
      : { hour: 'numeric', minute: '2-digit', ...(days ? { month: 'short', day: 'numeric' } : {}) }
  return new Intl.DateTimeFormat(locale, options).format(new Date(start))
}

/** The bars of the volume chart: when each begins, and how many events it had at each severity. */
export function volumeBars(volume: LogVolume, locale?: string): VolumeBars {
  const first = Date.parse(volume.start)
  const width = volume.seconds * 1000
  const starts = volume.counts.map((_, index) => first + index * width)
  const last = starts.at(-1) ?? first
  const days = new Date(first).toDateString() !== new Date(last).toDateString()
  return {
    categories: starts.map((start) => barLabel(start, volume.seconds, days, locale)),
    series: SEVERITIES.flatMap((severity, level) => {
      const values = volume.counts.map((bar) => bar[level] ?? 0)
      return values.some((count) => count > 0)
        ? [
            {
              id: severity,
              label: SEVERITY[severity].label,
              values,
              color: severityColor(severity),
              icon: SEVERITY[severity].icon,
            },
          ]
        : []
    }),
    ranges: starts.map((start) => ({ start: seconds(start), end: seconds(start + width) })),
  }
}

const TIME_TERMS = /(^|\s)-?(?:since|before)[:=](?:"[^"]*"|\S+)/gi

/** The search narrowed to a stretch of time, in place of any time it was narrowed to before. */
export function withinRange(text: string, { start, end }: { start: string; end: string }): string {
  const rest = text.replace(TIME_TERMS, ' ').replaceAll(/\s+/g, ' ').trim()
  const range = `since:${start} before:${end}`
  return rest ? `${rest} ${range}` : range
}

// ---------------------------------------------------------------------------------------------
// The table

export const COLUMNS = [
  { key: 'time', label: 'Time', fixed: true },
  { key: 'severity', label: 'Severity', fixed: false },
  { key: 'source', label: 'Source', fixed: false },
  { key: 'kind', label: 'Kind', fixed: false },
  { key: 'from', label: 'From', fixed: false },
  { key: 'to', label: 'To', fixed: false },
  { key: 'protocol', label: 'Protocol', fixed: false },
  { key: 'signature', label: 'Rule', fixed: false },
  { key: 'connection', label: 'Connection', fixed: false },
  { key: 'received', label: 'Received', fixed: false },
  { key: 'summary', label: 'Summary', fixed: true },
] as const

export type ColumnKey = (typeof COLUMNS)[number]['key']
export type TimeMode = 'exact' | 'relative'

export const DEFAULT_COLUMNS: readonly ColumnKey[] = [
  'time',
  'severity',
  'source',
  'kind',
  'from',
  'to',
  'summary',
]
export const COLUMNS_KEY = 'aresgate.logs.columns'
export const TIME_KEY = 'aresgate.logs.time'

function stored(key: string): unknown {
  try {
    return JSON.parse(localStorage.getItem(key) ?? 'null')
  } catch {
    return null
  }
}

function keep(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage can be unavailable; the choice still holds for this visit.
  }
}

/** The columns to show, in their own order: the ones this browser remembers, always with the
 * time and the summary, or the usual ones. */
export function readColumns(): ColumnKey[] {
  const found = stored(COLUMNS_KEY)
  const chosen = Array.isArray(found) ? (found as unknown[]) : [...DEFAULT_COLUMNS]
  return COLUMNS.filter(({ key, fixed }) => fixed || chosen.includes(key)).map(({ key }) => key)
}

export function writeColumns(columns: readonly ColumnKey[]): void {
  keep(COLUMNS_KEY, columns)
}

export function readTimeMode(): TimeMode {
  return stored(TIME_KEY) === 'relative' ? 'relative' : 'exact'
}

export function writeTimeMode(mode: TimeMode): void {
  keep(TIME_KEY, mode)
}

export type TableRow =
  { type: 'day'; key: string; label: string } | { type: 'event'; event: LogEvent }

const dayOf = (iso: string) => {
  const date = new Date(iso)
  return `${date.getFullYear().toString()}-${date.getMonth().toString()}-${date.getDate().toString()}`
}

/** The events as rows of a table, with a heading before the first of each day. */
export function tableRows(
  events: readonly LogEvent[],
  withDays: boolean,
  now = Date.now(),
  locale?: string,
): TableRow[] {
  const rows: TableRow[] = []
  let day = ''
  for (const event of events) {
    const key = dayOf(event.at)
    if (withDays && key !== day) {
      rows.push({ type: 'day', key, label: formatDay(event.at, now, locale) })
      day = key
    }
    rows.push({ type: 'event', event })
  }
  return rows
}

// ---------------------------------------------------------------------------------------------
// The drawer

export interface DetailField {
  id: string
  name: string
  value: string
  /** What to copy, where it is not what is shown. */
  copy?: string
  /** The search for events that are alike in this: put into the box, it narrows to them. */
  term?: string | undefined
}

/** A value as a search says it, or nothing where it can't be said (it holds a quote). */
function asked(field: string, value: string): string | undefined {
  if (value.includes('"')) return undefined
  return /[\s,]/.test(value) ? `${field}:"${value}"` : `${field}:${value}`
}

/** What is known of an event, a line for each thing, as the drawer lists it. */
export function fieldsOf(event: LogEvent, locale?: string): DetailField[] {
  const fields: DetailField[] = [
    { id: 'time', name: 'Time', value: formatTimestamp(event.at, locale), copy: event.at },
    {
      id: 'received',
      name: 'Received',
      value: formatTimestamp(event.received_at, locale),
      copy: event.received_at,
    },
    {
      id: 'severity',
      name: 'Severity',
      value: SEVERITY[event.severity].label,
      term: `severity:${event.severity}`,
    },
    { id: 'source', name: 'Source', value: event.source_name, term: asked('source', event.source) },
    {
      id: 'connection',
      name: 'Connection',
      value: event.connection,
      term: asked('connection', event.connection),
    },
    { id: 'kind', name: 'Kind', value: event.kind, term: asked('kind', event.kind) },
  ]
  const maybe = (id: string, name: string, value: string | number | null, field: string) => {
    if (value === null || value === '') return
    const text = value.toString()
    fields.push({ id, name, value: text, term: asked(field, text) })
  }
  maybe('signature', 'Rule', event.signature, 'signature')
  maybe('from', 'From', event.src_address, 'from')
  maybe('from-port', 'From port', event.src_port, 'sport')
  maybe('to', 'To', event.dst_address, 'to')
  maybe('to-port', 'To port', event.dst_port, 'port')
  maybe('protocol', 'Protocol', event.protocol, 'protocol')
  return fields
}

// ---------------------------------------------------------------------------------------------
// The program's own record

export interface JsonToken {
  /** `plain` is the brackets, commas and spacing between the parts that are coloured. */
  kind: 'key' | 'string' | 'number' | 'literal' | 'plain'
  text: string
}

const JSON_TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(true|false|null)|([{}[\],:]|\s+)/g

/** A record as pretty-printed text. */
export function rawText(raw: unknown): string {
  return JSON.stringify(raw, null, 2)
}

/** Pretty-printed JSON in parts, so that a page can colour keys, strings and numbers without
 * handing the text to the browser as markup. */
export function jsonTokens(text: string): JsonToken[] {
  const tokens: JsonToken[] = []
  const push = (kind: JsonToken['kind'], part: string) => {
    const previous = tokens.at(-1)
    if (kind === 'plain' && previous?.kind === 'plain') previous.text += part
    else tokens.push({ kind, text: part })
  }
  let end = 0
  for (const found of text.matchAll(JSON_TOKEN)) {
    if (found.index > end) push('plain', text.slice(end, found.index))
    const [whole, quoted, colon, number, literal] = found
    if (quoted !== undefined) {
      push(colon === undefined ? 'string' : 'key', quoted)
      if (colon !== undefined) push('plain', colon)
    } else if (number !== undefined) push('number', number)
    else if (literal !== undefined) push('literal', literal)
    else push('plain', whole)
    end = found.index + whole.length
  }
  if (end < text.length) push('plain', text.slice(end))
  return tokens
}
