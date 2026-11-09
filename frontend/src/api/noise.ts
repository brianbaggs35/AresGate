import { apiGet, apiPost, apiPut } from '@/api/client'
import type { Severity } from '@/severity'

/** The lowest severity that counts for a program. Anything lower is kept and listed, and set
 * aside: it no longer adds to how serious or how sure an incident is. */
export const FLOORS = ['medium', 'high', 'critical'] as const
export type Floor = (typeof FLOORS)[number]

/** A program that reported alerts, and what it reported in the last week. */
export interface NoiseSource {
  key: string
  name: string
  /** The lowest severity that counts, or null when every alert does. */
  floor: Floor | null
  week: Partial<Record<Severity, number>>
}

/** The noise filters as they are kept. */
export interface NoiseFilters {
  /** How sure AresGate has to be of an incident, from 1 to 100, for it to ask about it. */
  confidence_floor: number
  /** What it is until it is changed, and where the words medium and high are drawn. */
  default_floor: number
  medium_from: number
  high_from: number
  /** Whether alerts between two addresses on your own network are set aside. */
  quiet_inside: boolean
  /** How long a scan or a brute force may go quiet before its next signal is another incident. */
  scan_gap_hours: number
  default_scan_gap_hours: number
  brute_force_gap_hours: number
  default_brute_force_gap_hours: number
  /** The fewest low alerts from one program an incident needs before it is asked about; 1 is none. */
  thin_low_signals: number
  default_thin_low_signals: number
  sources: NoiseSource[]
  /** How many verdicts there are, which set signals aside too. */
  verdicts: number
  updated_at: string | null
}

/** What is changed when saving, which is all of it. */
export interface NoiseDraft {
  confidence_floor: number
  quiet_inside: boolean
  source_floors: Record<string, Floor>
  scan_gap_hours: number
  brute_force_gap_hours: number
  thin_low_signals: number
}

/** The incidents that are going on, by how they stand. */
export interface Tally {
  active: number
  needs_you: number
  urgent: number
  unsure: number
  cleared: number
  muted: number
}

/** The signals of those incidents that the filters set aside, and why. */
export interface SetAside {
  total: number
  inside: number
  severity: number
  thin: number
  by_source: Record<string, number>
}

export interface Effect {
  incidents: Tally
  set_aside: SetAside
  /** The gaps and the minimum the incidents above were judged by. */
  scan_gap_hours: number
  brute_force_gap_hours: number
  thin_low_signals: number
}

/** What the filters do now, and what they would do as asked. */
export interface Preview {
  now: Effect
  after: Effect
}

export function fetchNoiseFilters(): Promise<NoiseFilters> {
  return apiGet<NoiseFilters>('/noise-filters')
}

/** Keeps the filters. The incidents that are going on are judged again at once. */
export function saveNoiseFilters(draft: NoiseDraft, csrfToken: string): Promise<NoiseFilters> {
  return apiPut<NoiseFilters>('/noise-filters', draft, csrfToken)
}

/** What the filters would do if they were as asked. Nothing is kept. */
export function previewNoiseFilters(draft: NoiseDraft, csrfToken: string): Promise<Preview> {
  return apiPost<Preview>('/noise-filters/preview', draft, csrfToken)
}
