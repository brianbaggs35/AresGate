import type { Incident } from '@/api/incidents'
import { SEVERITIES, type Severity } from '@/severity'

/** What the table of incidents can be sorted by. */
export type SortKey =
  'severity' | 'title' | 'subject' | 'confidence' | 'status' | 'seen' | 'signals'

export type Direction = 'asc' | 'desc'

export interface Sort {
  key: SortKey
  direction: Direction
}

/** The columns, in order. `first` is the way a first press sorts: the most serious, the newest
 * or the biggest first for numbers and times, and A to Z for words. */
export const COLUMNS: readonly { key: SortKey; label: string; first: Direction }[] = [
  { key: 'severity', label: 'Severity', first: 'desc' },
  { key: 'title', label: 'Incident', first: 'asc' },
  { key: 'subject', label: 'About', first: 'asc' },
  { key: 'confidence', label: 'Confidence', first: 'desc' },
  { key: 'status', label: 'Status', first: 'asc' },
  { key: 'seen', label: 'Last seen', first: 'desc' },
  { key: 'signals', label: 'Signals', first: 'desc' },
]

/** What a press on a column does next: sorts it its natural way, then the other way, then goes
 * back to the order the API sent, which is the most urgent first. */
export function nextSort(current: Sort | null, key: SortKey): Sort | null {
  const first = (COLUMNS.find((column) => column.key === key) as (typeof COLUMNS)[number]).first
  if (current?.key !== key) return { key, direction: first }
  if (current.direction === first) return { key, direction: first === 'asc' ? 'desc' : 'asc' }
  return null
}

function valueOf(incident: Incident, key: SortKey): number | string {
  switch (key) {
    case 'severity':
      return SEVERITIES.indexOf(incident.severity)
    case 'title':
      return incident.title
    case 'subject':
      return incident.subject
    case 'confidence':
      return incident.confidence
    case 'status':
      return incident.status
    case 'seen':
      return Date.parse(incident.last_seen_at)
    case 'signals':
      return incident.signal_count
  }
}

/** The incidents in the order asked for, ties kept as they came. Only the incidents that are on
 * screen are sorted: the list is as long as the API has sent so far. */
export function sortedBy(incidents: readonly Incident[], sort: Sort | null): Incident[] {
  if (!sort) return [...incidents]
  const sign = sort.direction === 'asc' ? 1 : -1
  return incidents
    .map((incident, index) => ({ incident, index, value: valueOf(incident, sort.key) }))
    .sort((a, b) => {
      const by =
        typeof a.value === 'number' && typeof b.value === 'number'
          ? a.value - b.value
          : String(a.value).localeCompare(String(b.value))
      return by * sign || a.index - b.index
    })
    .map(({ incident }) => incident)
}

/** A run of the table: incidents about one address together under a heading, or one that stands
 * alone. */
export type Section =
  | { kind: 'alone'; incident: Incident }
  | { kind: 'group'; subject: string; members: Incident[]; worst: Severity }

/** The incidents with those about the same address gathered under it. An address with a single
 * incident is not a group, and a group sits where its first incident was, so the order of the
 * list, whichever way it was sorted, still holds. */
export function groupedByAddress(incidents: readonly Incident[]): Section[] {
  const by = new Map<string, Incident[]>()
  for (const incident of incidents) {
    by.set(incident.subject, [...(by.get(incident.subject) ?? []), incident])
  }
  const done = new Set<string>()
  const sections: Section[] = []
  for (const incident of incidents) {
    const members = by.get(incident.subject) as Incident[]
    if (members.length === 1) {
      sections.push({ kind: 'alone', incident })
    } else if (!done.has(incident.subject)) {
      done.add(incident.subject)
      const worst = members.reduce<Severity>(
        (top, member) =>
          SEVERITIES.indexOf(member.severity) > SEVERITIES.indexOf(top) ? member.severity : top,
        'info',
      )
      sections.push({ kind: 'group', subject: incident.subject, members, worst })
    }
  }
  return sections
}
