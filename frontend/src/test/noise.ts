import type { Effect, NoiseFilters, NoiseSource, Preview } from '@/api/noise'

/** Wazuh, which reported a lot of low alerts this week, with every alert counting. */
export function source(changes: Partial<NoiseSource> = {}): NoiseSource {
  return {
    key: 'wazuh',
    name: 'Wazuh',
    floor: null,
    week: { low: 2901, medium: 150, high: 12 },
    ...changes,
  }
}

/** The noise filters as they are before anyone has changed them, for an install with Wazuh and
 * ntopng reporting alerts, with whatever is given changed. */
export function noiseFilters(changes: Partial<NoiseFilters> = {}): NoiseFilters {
  return {
    confidence_floor: 35,
    default_floor: 35,
    medium_from: 35,
    high_from: 65,
    quiet_inside: false,
    sources: [source(), source({ key: 'ntopng', name: 'ntopng', week: { medium: 40 } })],
    verdicts: 3,
    updated_at: null,
    ...changes,
  }
}

/** What the filters do to the incidents that are going on: 31 of them, 5 needing you, nothing
 * set aside, with whatever is given changed. */
export function effect(changes: Partial<Effect> = {}): Effect {
  return {
    incidents: { active: 31, needs_you: 5, urgent: 1, unsure: 24, muted: 2 },
    set_aside: { total: 0, inside: 0, severity: 0, by_source: {} },
    ...changes,
  }
}

/** A preview in which the filters leave 2 incidents needing you and set 2,901 alerts aside. */
export function preview(changes: Partial<Preview> = {}): Preview {
  return {
    now: effect(),
    after: effect({
      incidents: { active: 31, needs_you: 2, urgent: 0, unsure: 27, muted: 2 },
      set_aside: { total: 2901, inside: 0, severity: 2901, by_source: { wazuh: 2901 } },
    }),
    ...changes,
  }
}
