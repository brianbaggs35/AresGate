import type { Choice, Choices, Detail, Rules } from '@/api/alerts'

/** How serious an incident is, as the rules ask for it. The numbers are the severities of the
 * API (info is 0 and never worth a message). */
export const SEVERITIES: readonly { value: number; label: string }[] = [
  { value: 1, label: 'Low or worse' },
  { value: 2, label: 'Medium or worse' },
  { value: 3, label: 'High or worse' },
  { value: 4, label: 'Critical only' },
]

/** How sure AresGate is, in the three bands the Incidents page draws: low below 35, high from 65. */
export const CONFIDENCES: readonly { value: number; label: string }[] = [
  { value: 65, label: 'High: 65% or more' },
  { value: 35, label: 'Medium or more: 35% or more' },
  { value: 0, label: 'Any, however unsure' },
]

/** How many messages an hour a destination may get, before the rest are put in one. */
export const PER_HOUR: readonly number[] = [1, 2, 3, 6, 10, 20, 60]

export const DETAILS: readonly { value: Detail; label: string; text: string }[] = [
  {
    value: 'brief',
    label: 'Brief',
    text: 'What happened and how serious, with a link. No addresses.',
  },
  {
    value: 'standard',
    label: 'Standard',
    text: 'Adds the address on the internet that did it and the programs that saw it. Devices on your network are only called "a device on your network".',
  },
  {
    value: 'full',
    label: 'Full',
    text: 'Also names the devices on your network by address. Discord keeps what is posted there, so choose this only for a channel only you can read.',
  },
]

/** The choices for a number the rules hold, with the current one added if the list lacks it (a
 * value set by something other than this page). */
export function withCurrent(
  choices: readonly { value: number; label: string }[],
  current: number,
  label: (value: number) => string,
): { value: number; label: string }[] {
  return choices.some((choice) => choice.value === current)
    ? [...choices]
    : [...choices, { value: current, label: label(current) }].sort((a, b) => b.value - a.value)
}

export function perHour(value: number): string {
  return value === 1 ? 'At most 1 message an hour' : `At most ${value.toString()} messages an hour`
}

/** Minutes after midnight as the `HH:MM` a time field holds. */
export function toTime(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  return `${hours.toString().padStart(2, '0')}:${(minutes % 60).toString().padStart(2, '0')}`
}

/** The minutes after midnight in an `HH:MM` time, or none if it isn't one. */
export function toMinutes(time: string): number | null {
  const found = /^(\d{2}):(\d{2})$/.exec(time)
  if (!found) return null
  const minutes = Number(found[1]) * 60 + Number(found[2])
  return Number(found[1]) < 24 && Number(found[2]) < 60 ? minutes : null
}

/** The time zone this computer's clock is in, to start quiet hours in. */
export function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

function listed(names: string[]): string {
  const last = names.slice(-1).join('')
  return names.length < 2 ? last : `${names.slice(0, -1).join(', ')} and ${last}`
}

function named(keys: string[], choices: Choice[]): string[] {
  return keys.map((key) => choices.find((choice) => choice.key === key)?.name ?? key)
}

/** What a destination is told about, in a few sentences for its card. */
export function describeRules(rules: Rules, choices: Choices): string {
  const severity = (
    SEVERITIES.find((item) => item.value === rules.min_severity)?.label ??
    `Severity ${rules.min_severity.toString()} or worse`
  ).toLowerCase()
  const sure =
    rules.min_confidence === 0
      ? 'however sure AresGate is'
      : `when AresGate is at least ${rules.min_confidence.toString()}% sure`
  const parts = [`Tells you about incidents that are ${severity}, ${sure}`]
  parts.push(
    rules.sources.length > 0
      ? `Only from ${listed(named(rules.sources, choices.sources))}`
      : 'From any program',
  )
  if (rules.activities.length > 0) {
    parts.push(`Only ${listed(named(rules.activities, choices.activities))}`)
  }
  parts.push(perHour(rules.max_per_hour))
  if (rules.quiet_hours) {
    const critical = rules.quiet_critical ? ', except critical ones' : ''
    parts.push(
      `Quiet from ${toTime(rules.quiet_from)} to ${toTime(rules.quiet_until)} (${rules.time_zone})${critical}`,
    )
  }
  return `${parts.join('. ')}.`
}
