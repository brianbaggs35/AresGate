import type { FilteredBy } from '@/api/incidents'
import type { Effect, Floor, NoiseDraft, NoiseFilters, NoiseSource, Preview } from '@/api/noise'
import { formatCount } from '@/format'
import { SEVERITY, SEVERITIES } from '@/severity'

/** The slider's ends and steps. */
export const FLOOR_MIN = 5
export const FLOOR_MAX = 95
export const FLOOR_STEP = 5

/** What a program's select offers: everything it reports, or only from a severity up. */
export const ALL = 'all'
export const FLOOR_CHOICES: readonly { value: Floor | typeof ALL; title: string }[] = [
  { value: ALL, title: 'Everything it reports' },
  { value: 'medium', title: 'Medium and up' },
  { value: 'high', title: 'High and up' },
  { value: 'critical', title: 'Critical only' },
]

/** The draft that saving would keep, to begin with what is kept. */
export function draftOf(kept: NoiseFilters): NoiseDraft {
  return {
    confidence_floor: kept.confidence_floor,
    quiet_inside: kept.quiet_inside,
    source_floors: Object.fromEntries(
      kept.sources.flatMap(({ key, floor }) => (floor ? [[key, floor] as const] : [])),
    ),
  }
}

/** Whether two drafts say the same. */
export function sameDraft(one: NoiseDraft, other: NoiseDraft): boolean {
  const mine = Object.entries(one.source_floors)
  return (
    one.confidence_floor === other.confidence_floor &&
    one.quiet_inside === other.quiet_inside &&
    mine.length === Object.keys(other.source_floors).length &&
    mine.every(([key, floor]) => other.source_floors[key] === floor)
  )
}

/** The draft with a program's floor set, or taken off (`ALL`). */
export function withFloor(draft: NoiseDraft, key: string, floor: Floor | typeof ALL): NoiseDraft {
  const others = Object.entries(draft.source_floors).filter(([name]) => name !== key)
  const source_floors = Object.fromEntries(floor === ALL ? others : [...others, [key, floor]])
  return { ...draft, source_floors }
}

/** The word for how sure that is, where the server draws its lines. */
export function levelOf(floor: number, mediumFrom: number, highFrom: number): string {
  if (floor >= highFrom) return 'high'
  return floor >= mediumFrom ? 'medium' : 'low'
}

/** What a floor means, in a sentence. */
export function floorSentence(floor: number, mediumFrom: number, highFrom: number): string {
  const level = levelOf(floor, mediumFrom, highFrom)
  const reach = {
    low: 'Low is a long way down: you will hear about a lot, including things that are probably nothing.',
    medium:
      'That is medium confidence and up: what AresGate has more than one reason to doubt is left out.',
    high: 'That is high confidence and up: you hear only about what it is nearly sure is real.',
  }[level]
  return `AresGate asks about an incident once it is at least ${floor.toString()} sure it is real. ${reach}`
}

/** What a program reported in the last week, most serious first. */
export function weekSentence(source: Pick<NoiseSource, 'week'>): string {
  const parts = [...SEVERITIES].reverse().flatMap((level) => {
    const count = source.week[level]
    return count ? [`${formatCount(count)} ${SEVERITY[level].label.toLowerCase()}`] : []
  })
  return parts.length ? `Last 7 days: ${parts.join(', ')}.` : 'Nothing in the last 7 days.'
}

/** How many incidents are filtered out: AresGate is not sure enough of them, or a verdict of
 * yours says they are nothing. */
export function filteredOut(effect: Effect): number {
  return effect.incidents.unsure + effect.incidents.muted
}

/** The figures of a preview, for the table that sets now beside what it would be. */
export function rowsOf(
  preview: Preview,
): { key: string; label: string; now: number; after: number }[] {
  return [
    {
      key: 'needs-you',
      label: 'Incidents that need you',
      now: preview.now.incidents.needs_you,
      after: preview.after.incidents.needs_you,
    },
    {
      key: 'filtered-out',
      label: 'Incidents filtered out',
      now: filteredOut(preview.now),
      after: filteredOut(preview.after),
    },
    {
      key: 'set-aside',
      label: 'Alerts set aside inside them',
      now: preview.now.set_aside.total,
      after: preview.after.set_aside.total,
    },
  ]
}

function counted(count: number, one: string, many: string): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`
}

/** What saving would do, in a sentence for someone who can't see the table. */
export function changeSentence(preview: Preview): string {
  const { now, after } = preview
  const needing = after.incidents.needs_you
  const incidents = counted(needing, 'incident', 'incidents')
  const wording =
    needing === now.incidents.needs_you
      ? `${incidents} would still need you`
      : `${incidents} would need you instead of ${formatCount(now.incidents.needs_you)}`
  const aside = counted(after.set_aside.total, 'alert', 'alerts')
  return `With these settings ${wording}, and ${aside} would be set aside.`
}

/** Why a signal was set aside, for the chip on it in the timeline. */
export const SET_ASIDE: Readonly<Record<FilteredBy, string>> = {
  inside: 'Set aside: inside your network',
  severity: "Set aside: under this program's severity",
}
