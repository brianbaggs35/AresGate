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

/** How long a scan or a brute force may go quiet before its next signal is another incident: the
 * whole hours the owner can choose from. */
export const GAP_HOURS: readonly number[] = Array.from({ length: 24 }, (_, index) => index + 1)
export const GAP_CHOICES: readonly { value: number; title: string }[] = GAP_HOURS.map((hours) => ({
  value: hours,
  title: hoursText(hours),
}))
/** The fewest low alerts from one program that an incident needs before it is asked about. One is
 * no minimum at all. */
export const THIN_MIN = 1
export const THIN_MAX = 10
export const THIN_CHOICES: readonly { value: number; title: string }[] = Array.from(
  { length: THIN_MAX - THIN_MIN + 1 },
  (_, index) => {
    const value = THIN_MIN + index
    return {
      value,
      title: value === THIN_MIN ? '1 (no minimum)' : `${value.toString()} low alerts`,
    }
  },
)

/** A number of hours, in words. */
export function hoursText(hours: number): string {
  return hours === 1 ? '1 hour' : `${hours.toString()} hours`
}

/** What the two gaps say, in a sentence. */
export function gapSentence(scanHours: number, bruteForceHours: number): string {
  return `A scan that goes quiet for less than ${hoursText(scanHours)} is still one incident, and so is a brute force that goes quiet for less than ${hoursText(bruteForceHours)}. A longer quiet starts another incident.`
}

/** What the minimum says, in a sentence. */
export function thinSentence(minimum: number): string {
  if (minimum <= THIN_MIN) {
    return 'No minimum: every incident is asked about, as it was before this setting.'
  }
  return `An incident of one program's low alerts is asked about once it has ${minimum.toString()} of them. A lone low alert is never asked about.`
}

/** The draft that saving would keep, to begin with what is kept. */
export function draftOf(kept: NoiseFilters): NoiseDraft {
  return {
    confidence_floor: kept.confidence_floor,
    quiet_inside: kept.quiet_inside,
    scan_gap_hours: kept.scan_gap_hours,
    brute_force_gap_hours: kept.brute_force_gap_hours,
    thin_low_signals: kept.thin_low_signals,
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
    one.scan_gap_hours === other.scan_gap_hours &&
    one.brute_force_gap_hours === other.brute_force_gap_hours &&
    one.thin_low_signals === other.thin_low_signals &&
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

/** What a change of the two gaps, or of the minimum, comes to, in sentences of its own. */
function settingSentences({ now, after }: Preview): string[] {
  const parts: string[] = []
  if (
    now.scan_gap_hours !== after.scan_gap_hours ||
    now.brute_force_gap_hours !== after.brute_force_gap_hours
  ) {
    parts.push(
      `From now on a scan starts another incident after a quiet of ${hoursText(after.scan_gap_hours)}, and a brute force after ${hoursText(after.brute_force_gap_hours)}. Incidents already made keep their grouping.`,
    )
  }
  if (now.thin_low_signals !== after.thin_low_signals) {
    parts.push(thinSentence(after.thin_low_signals))
  }
  return parts
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
  const sentence = `With these settings ${wording}, and ${aside} would be set aside.`
  return [sentence, ...settingSentences(preview)].join(' ')
}

/** Why a signal was set aside, for the chip on it in the timeline. */
export const SET_ASIDE: Readonly<Record<FilteredBy, string>> = {
  inside: 'Set aside: inside your network',
  severity: "Set aside: under this program's severity",
  thin: "Set aside: one program's low alerts, too few to ask about",
}
