import { CircleQuestionMark, Radar, ShieldAlert, Swords, VolumeX } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Classification, IncidentDetail, Reading } from '@/api/incidents'
import { formatAgo } from '@/format'

interface ClassificationLook {
  label: string
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** What the AI means by it, in a sentence. */
  meaning: string
}

/** What each kind of thing an AI can make of an incident looks like. Like a severity, never just
 * a color: each has its icon and its name. */
export const CLASSIFICATION: Readonly<Record<Classification, ClassificationLook>> = {
  compromise: {
    label: 'Possible compromise',
    color: 'error',
    icon: ShieldAlert,
    meaning: 'Something on your network looks infected, taken over or leaking data.',
  },
  attack: {
    label: 'Active attack',
    color: 'error',
    icon: Swords,
    meaning: 'A targeted attack from outside that deserves your attention.',
  },
  probe: {
    label: 'Probe',
    color: 'warning',
    icon: Radar,
    meaning: 'Scanning or guessing with no sign that it worked: routine background.',
  },
  noise: {
    label: 'Harmless',
    color: 'success',
    icon: VolumeX,
    meaning: 'Normal traffic or a rule that fires on normal things.',
  },
  unclear: {
    label: 'Unclear',
    color: 'info',
    icon: CircleQuestionMark,
    meaning: 'There is too little evidence to tell.',
  },
}

/** Who read it and when, for the line under the reading. */
export function readBy(reading: Reading): string {
  return `Read by ${reading.provider} (${reading.model}) ${formatAgo(reading.read_at)}.`
}

/** How many signals came in after it was read, which makes it worth reading again. */
export function newSince(incident: Pick<IncidentDetail, 'signal_count' | 'reading'>): number {
  return incident.reading ? Math.max(0, incident.signal_count - incident.reading.signals_read) : 0
}

/** Whether the AI has yet to read the incident, or has not read all of it. */
export function needsReading(incident: Pick<IncidentDetail, 'signal_count' | 'reading'>): boolean {
  return !incident.reading || newSince(incident) > 0
}

/** The new signals, in words. */
export function newSignals(count: number): string {
  return count === 1
    ? '1 new signal has come in since.'
    : `${count.toString()} new signals have come in since.`
}
