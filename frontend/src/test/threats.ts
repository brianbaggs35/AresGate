import type { Coverage, Family, FamilyDetail, Funnel, Overview } from '@/api/threats'
import type { ThreatPreview, ThreatSettings } from '@/api/threatSettings'

import { dashboard } from '@/test/dashboard'
import { incident } from '@/test/incidents'

const NOW = Date.now()
const HOUR = 3_600_000

/** The funnel of a busy day: seventy thousand reports that came to a few incidents. */
export function funnel(changes: Partial<Funnel> = {}): Funnel {
  return {
    reports: 70_412,
    duplicates: 31_000,
    repeats: 38_208,
    alerts: 1_204,
    incidents: 63,
    families: 9,
    threats: 2,
    suspects: 5,
    background: 50,
    muted: 4,
    handled: 2,
    ...changes,
  }
}

export function coverage(changes: Partial<Coverage> = {}): Coverage {
  return { families: 9, judged: 6, owned: 1, waiting: 2, ...changes }
}

/** A kind of incident that is going on: a scan of the network from the internet, which the AI
 * judged to be a probe. */
export function family(changes: Partial<Family> = {}): Family {
  return {
    id: 7,
    label: 'ET SCAN Potential SSH Scan from <address>',
    source: 'opnsense',
    source_name: 'OPNsense',
    reach: 'internet',
    owner_call: null,
    classification: 'probe',
    confidence: 92,
    reason: 'Internet scanners probing ssh, with nothing open.',
    judged_at: new Date(NOW - 3 * HOUR).toISOString(),
    incidents: 41,
    alerts: 3_200,
    actors: 41,
    worst: 'medium',
    first_seen_at: new Date(NOW - 20 * HOUR).toISOString(),
    last_seen_at: new Date(NOW - 5 * 60_000).toISOString(),
    threats: 0,
    suspects: 1,
    background: 40,
    ...changes,
  }
}

export function overview(changes: Partial<Overview> = {}): Overview {
  const { window } = dashboard()
  return {
    window,
    funnel: funnel(),
    coverage: coverage(),
    watching: true,
    threat_from: 65,
    families: [family()],
    ...changes,
  }
}

/** One kind with all it knows: who judged it, why it is where it is and its incidents. */
export function familyDetail(changes: Partial<FamilyDetail> = {}): FamilyDetail {
  return {
    ...family(),
    provider: 'Anthropic',
    model: 'claude-haiku-5-5',
    owner_call_at: null,
    why: ['The AI is 92% sure this kind is a probe, so its incidents are background.'],
    sample: [incident({ id: 3, lane: 'background', family_id: 7 })],
    ...changes,
  }
}

export function threatSettings(changes: Partial<ThreatSettings> = {}): ThreatSettings {
  return {
    threat_from: 65,
    ai_may_clear: true,
    clear_from: 80,
    ai_confirms: true,
    exposure: 'unknown',
    exposed_ports: [],
    notes: '',
    default_threat_from: 65,
    default_clear_from: 80,
    min_clear_from: 50,
    max_notes: 500,
    max_ports: 20,
    watching: true,
    updated_at: null,
    ...changes,
  }
}

export function threatPreview(changes: Partial<ThreatPreview> = {}): ThreatPreview {
  return {
    now: { threats: 2, suspects: 5, background: 50, cleared: 40, muted: 4 },
    after: { threats: 3, suspects: 4, background: 50, cleared: 40, muted: 4 },
    ...changes,
  }
}
