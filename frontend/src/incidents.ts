import { BellOff, CircleCheckBig, CircleDot, RotateCcw, Search } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type {
  ConfidenceLevel,
  Incident,
  IncidentPage,
  IncidentQuery,
  IncidentStatus,
  Program,
  Signal,
} from '@/api/incidents'
import { formatDuration } from '@/format'
import type { Severity } from '@/severity'

interface StatusLook {
  label: string
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** What the status means, in a sentence. */
  meaning: string
}

/** What each status looks like. Like a severity, never just a color: each has its icon and name. */
export const STATUS: Readonly<Record<IncidentStatus, StatusLook>> = {
  open: {
    label: 'Open',
    color: 'primary',
    icon: CircleDot,
    meaning: "Nobody has said they're looking at it.",
  },
  investigating: {
    label: 'Investigating',
    color: 'info',
    icon: Search,
    meaning: "You're looking into it.",
  },
  resolved: {
    label: 'Resolved',
    color: 'success',
    icon: CircleCheckBig,
    meaning: "It's over. A new signal about the same address starts another incident.",
  },
  dismissed: {
    label: 'Dismissed',
    color: 'secondary',
    icon: BellOff,
    meaning: "It isn't a threat. It keeps collecting signals, quietly.",
  },
}

/** A change of status someone can make, as the button for it. */
export interface StatusAction {
  status: IncidentStatus
  label: string
  icon: NonNullable<IconProps['icon']>
  /** The one to reach for first: it is filled where the others are outlined. */
  primary?: boolean
}

const INVESTIGATE: StatusAction = {
  status: 'investigating',
  label: 'Start investigating',
  icon: Search,
  primary: true,
}
const RESOLVE: StatusAction = { status: 'resolved', label: 'Resolve', icon: CircleCheckBig }
const DISMISS: StatusAction = { status: 'dismissed', label: 'Dismiss', icon: BellOff }
const REOPEN: StatusAction = { status: 'open', label: 'Reopen', icon: RotateCcw, primary: true }

/** What can be done about an incident in this status. */
export function actionsFor(status: IncidentStatus): readonly StatusAction[] {
  switch (status) {
    case 'open':
      return [INVESTIGATE, RESOLVE, DISMISS]
    case 'investigating':
      return [
        { ...RESOLVE, primary: true },
        DISMISS,
        { ...REOPEN, label: 'Back to open', primary: false },
      ]
    default:
      return [REOPEN]
  }
}

/** What a status's change reads like afterwards: "Marked as resolved." */
export function changedTo(status: IncidentStatus): string {
  return status === 'open' ? 'Reopened.' : `Marked as ${STATUS[status].label.toLowerCase()}.`
}

/** Low, medium and high, in the words people use. */
export const CONFIDENCE: Readonly<Record<ConfidenceLevel, string>> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

/** Where confidence passes to medium and to high. They are the API's (`rules.py`), repeated here
 * because a filter asks for "at least" a number. */
export const MEDIUM_CONFIDENCE = 35
export const HIGH_CONFIDENCE = 65

/** What a reason is called above its sentence. */
const REASONS: Readonly<Record<string, string>> = {
  strongest: 'Most serious signal',
  corroborated: 'Other programs agree',
  repeated: 'It keeps happening',
  banned: 'Banned',
  spread: 'It reaches several addresses',
  muted: 'Left out by your verdicts',
  threat: 'You said it is a real threat',
}

/** The name of a reason, or its key for one this version doesn't know. */
export function reasonLabel(rule: string): string {
  return REASONS[rule] ?? rule
}

/** The groups of incidents the list can show, by the statuses in each. */
export const VIEWS = [
  { key: 'active', label: 'Active', statuses: ['open', 'investigating'] },
  { key: 'open', label: 'Open', statuses: ['open'] },
  { key: 'investigating', label: 'Investigating', statuses: ['investigating'] },
  { key: 'resolved', label: 'Resolved', statuses: ['resolved'] },
  { key: 'dismissed', label: 'Dismissed', statuses: ['dismissed'] },
  { key: 'all', label: 'All', statuses: [] },
] as const satisfies readonly { key: string; label: string; statuses: readonly IncidentStatus[] }[]

export type ViewKey = (typeof VIEWS)[number]['key']

export const DEFAULT_VIEW: ViewKey = 'active'

/** How many incidents there are in a view. */
export function countIn(view: ViewKey, counts: IncidentPage['counts']): number {
  const { statuses } = VIEWS.find(({ key }) => key === view) as (typeof VIEWS)[number]
  const wanted: readonly IncidentStatus[] = statuses
  return wanted.length === 0
    ? Object.values(counts).reduce((sum, count) => sum + count, 0)
    : wanted.reduce((sum, status) => sum + counts[status], 0)
}

/** How serious an incident has to be to be listed. */
export const SEVERITY_FILTERS: readonly { value: Severity | null; label: string }[] = [
  { value: null, label: 'Any severity' },
  { value: 'medium', label: 'Medium or more' },
  { value: 'high', label: 'High or more' },
  { value: 'critical', label: 'Critical only' },
]

/** How sure AresGate has to be of it to be listed. */
export const CONFIDENCE_FILTERS: readonly { value: number; label: string }[] = [
  { value: 0, label: 'Any confidence' },
  { value: MEDIUM_CONFIDENCE, label: 'Medium or more' },
  { value: HIGH_CONFIDENCE, label: 'High only' },
]

/** What the list is narrowed to. */
export interface Filters {
  view: ViewKey
  severity: Severity | null
  confidence: number
  /** What was typed: an address only counts once it is whole. */
  address: string
  /** Whether to include the incidents the owner called not suspicious or low priority, which
   * the list leaves out unless asked. */
  quieted: boolean
}

export const NO_FILTERS: Readonly<Filters> = {
  view: DEFAULT_VIEW,
  severity: null,
  confidence: 0,
  address: '',
  quieted: false,
}

const IPV4 = /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/
const IPV6 = /^(?=(?:[^:]*:){2})[0-9a-f:.]{2,45}$/i

/** Whether text is a whole IP address, which is what the API takes to look for. */
export function isAddress(text: string): boolean {
  return IPV4.test(text) || IPV6.test(text)
}

/** The search for a list that is narrowed this way. */
export function queryOf(filters: Filters, limit: number): IncidentQuery {
  const { statuses } = VIEWS.find(({ key }) => key === filters.view) as (typeof VIEWS)[number]
  const address = filters.address.trim()
  return {
    statuses,
    ...(filters.severity ? { minSeverity: filters.severity } : {}),
    minConfidence: filters.confidence,
    ...(isAddress(address) ? { address } : {}),
    ...(filters.quieted ? {} : { verdicts: ['none', 'threat'] as const }),
    limit,
  }
}

/** How many filters other than the view are on, for the button that clears them. */
export function activeFilters(filters: Filters): number {
  return (
    Number(filters.severity !== null) +
    Number(filters.confidence !== 0) +
    Number(isAddress(filters.address.trim())) +
    Number(filters.quieted)
  )
}

/** How long an incident went on for, in words: "A single moment" or "Lasted 3h 12m". */
export function lasted(incident: Pick<Incident, 'first_seen_at' | 'last_seen_at'>): string {
  const seconds = (Date.parse(incident.last_seen_at) - Date.parse(incident.first_seen_at)) / 1000
  return seconds < 60 ? 'Under a minute' : formatDuration(seconds)
}

/** How long the signals of an incident took to come in, as it ends a sentence: "within a minute"
 * or "over 3h 12m". */
export function spanOf(incident: Pick<Incident, 'first_seen_at' | 'last_seen_at'>): string {
  const length = lasted(incident)
  return length === 'Under a minute' ? 'within a minute' : `over ${length}`
}

/** The other addresses an incident names besides the one it is about. */
export function otherAddresses(incident: Pick<Incident, 'subject' | 'addresses'>): string[] {
  return incident.addresses.filter((address) => address !== incident.subject)
}

/** Whether an incident is about a rule, because its signals named no address. */
export function isAboutRule(subject: string): boolean {
  return subject.startsWith('rule:')
}

/** One end of a connection: its address, with the port after it when there is one. An IPv6
 * address is in brackets then, so the port can be told from the rest of it. */
function endOf(address: string | null, port: number | null): string | null {
  if (address === null) return null
  if (port === null) return address
  const written = address.includes(':') ? `[${address}]` : address
  return `${written}:${port.toString()}`
}

/** The traffic a signal described, as "198.51.100.7:51514 → 192.168.1.20:22 (tcp)", or null for
 * a signal that named no address. */
export function flowOf(signal: Signal): string | null {
  const from = endOf(signal.src_address, signal.src_port)
  const to = endOf(signal.dst_address, signal.dst_port)
  let route: string
  if (from !== null && to !== null) route = `${from} → ${to}`
  else if (from !== null) route = from
  else if (to !== null) route = `→ ${to}`
  else return null
  return signal.protocol ? `${route} (${signal.protocol})` : route
}

const MINUTE = 60_000
/** The widths a bar of the chart can have, narrowest first. */
const DAY = 24 * 60 * MINUTE
const BUCKETS = [1, 5, 15, 30, 60, 180, 360, 720].map((minutes) => minutes * MINUTE).concat(DAY)
/** The most bars the chart has. */
const MAX_BARS = 24

/** An incident's signals counted over its time, for a chart. */
export interface Spread {
  /** When each bar starts, as a label. */
  categories: string[]
  /** One series for each program, in the order they are given. */
  series: { id: string; label: string; values: number[] }[]
  /** How wide a bar is, in words: "5 minutes". */
  width: string
}

function widthName(milliseconds: number): string {
  const minutes = milliseconds / MINUTE
  if (minutes < 60) return `${minutes.toString()} ${minutes === 1 ? 'minute' : 'minutes'}`
  const hours = minutes / 60
  return `${hours.toString()} ${hours === 1 ? 'hour' : 'hours'}`
}

/** Counts signals in bars of equal width, the narrowest that keeps them to a couple of dozen, for
 * each of the programs that reported them. */
export function spreadOf(
  signals: readonly Signal[],
  programs: readonly Program[],
  locale?: string,
): Spread {
  const times = signals.map(({ occurred_at: at }) => Date.parse(at))
  const first = Math.min(...times)
  const last = Math.max(...times)
  const bars = (width: number) => Math.floor((last - Math.floor(first / width) * width) / width) + 1
  const width = BUCKETS.find((candidate) => bars(candidate) <= MAX_BARS) ?? DAY
  const start = Math.floor(first / width) * width
  const count = bars(width)
  // Short stretches read as clock times, longer ones need the day.
  const options: Intl.DateTimeFormatOptions =
    width < 3 * 60 * MINUTE
      ? { hour: 'numeric', minute: '2-digit' }
      : { weekday: 'short', hour: 'numeric' }
  const label = new Intl.DateTimeFormat(locale, options)
  const series = programs.map(({ key, name }) => ({
    id: key,
    label: name,
    values: new Array<number>(count).fill(0),
  }))
  signals.forEach(({ source }, index) => {
    const bar = Math.floor(((times[index] as number) - start) / width)
    const found = series.find(({ id }) => id === source)
    if (found) (found.values[bar] as number) += 1
  })
  return {
    categories: Array.from({ length: count }, (_, bar) =>
      label.format(new Date(start + bar * width)),
    ),
    series,
    width: widthName(width),
  }
}
