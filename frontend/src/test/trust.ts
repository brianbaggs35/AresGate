import type { AppliedIncident, Suggestion, Trust, TrustDetail, TrustList } from '@/api/trust'

const NOW = Date.now()
const HOUR = 3_600_000

/** A decision that an address is safe, made yesterday and applied to 12 alerts in 2 incidents, the
 * last 2 hours ago, with whatever is given changed. */
export function trustRule(changes: Partial<Trust> = {}): Trust {
  return {
    id: 1,
    verdict: 'not_suspicious',
    about: 'Everything about 52.1.2.3',
    address: '52.1.2.3',
    destination: null,
    source: null,
    source_name: null,
    signature: null,
    note: null,
    created_at: new Date(NOW - 24 * HOUR).toISOString(),
    updated_at: new Date(NOW - 24 * HOUR).toISOString(),
    hits: 12,
    incidents: 2,
    last_hit_at: new Date(NOW - 2 * HOUR).toISOString(),
    ...changes,
  }
}

/** The decisions as the page lists them: a camera that is trusted to talk to its cloud, and an
 * address that is only low priority. */
export function trustList(changes: Partial<TrustList> = {}): TrustList {
  const camera = trustRule({
    id: 2,
    about: 'What 192.168.1.30 sends to 52.0.0.0/8',
    address: '192.168.1.30',
    destination: '52.0.0.0/8',
    note: 'Blink camera',
    hits: 1,
    incidents: 1,
  })
  const low = trustRule({
    id: 1,
    verdict: 'low_priority',
    hits: 0,
    incidents: 0,
    last_hit_at: null,
  })
  return { items: [camera, low], safe: 1, low_priority: 1, applied: 1, ...changes }
}

export function appliedIncident(changes: Partial<AppliedIncident> = {}): AppliedIncident {
  return {
    id: 7,
    title: 'ET MALWARE Possible beacon (52.1.2.3)',
    severity: 'critical',
    status: 'open',
    last_seen_at: new Date(NOW - 2 * HOUR).toISOString(),
    signals: 12,
    ...changes,
  }
}

export function trustDetail(changes: Partial<TrustDetail> = {}): TrustDetail {
  return { ...trustRule(), applied_to: [appliedIncident()], ...changes }
}

/** An incident the AI is quite sure is nothing, with a reason, unless given. */
export function suggestion(changes: Partial<Suggestion> = {}): Suggestion {
  return {
    incident_id: 9,
    title: 'ET SCAN Potential SSH Scan (93.184.216.34)',
    subject: '93.184.216.34',
    severity: 'medium',
    last_seen_at: new Date(NOW - HOUR).toISOString(),
    verdict: 'not_suspicious',
    confidence: 90,
    headline: 'A vendor’s own scanner',
    reason: 'It scans on a schedule.',
    ...changes,
  }
}
