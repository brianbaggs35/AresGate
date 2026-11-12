import type { Decision, ReviewPage, ReviewSettings } from '@/api/review'

const NOW = Date.parse('2026-06-01T12:00:00Z')

/** A decision waiting for the owner: the AI set a scan of ssh aside as a probe. */
export function decision(changes: Partial<Decision> = {}): Decision {
  return {
    subject: 'family',
    id: 7,
    review: 'pending',
    kind: 'probe',
    confidence: 92,
    title: 'ET SCAN Potential SSH Scan from <address>',
    why: 'Internet scanners probing ssh, with nothing open.',
    suggestion: null,
    decided_at: new Date(NOW - 3_600_000).toISOString(),
    reviewed_at: null,
    incidents: 41,
    active: 41,
    severity: 'medium',
    provider: 'Anthropic',
    model: 'claude-haiku-5-5',
    reason: null,
    counting: false,
    effect: 'Sets aside 41 incidents going on, and any more of this kind.',
    ...changes,
  }
}

/** A page of the Review lists. */
export function reviewPage(changes: Partial<ReviewPage> = {}): ReviewPage {
  return {
    state: 'waiting',
    total: 1,
    items: [decision()],
    counts: { waiting: 1, decided: 2, answered: 3 },
    standing: {
      agreed: 0,
      disagreed: 0,
      rate: null,
      trusted: false,
      trust_after: 20,
      trust_rate: 0.95,
    },
    mode: 'all',
    ...changes,
  }
}

export function reviewSettings(changes: Partial<ReviewSettings> = {}): ReviewSettings {
  return {
    mode: 'all',
    auto_from: 85,
    learn: true,
    default_mode: 'all',
    default_auto_from: 85,
    min_auto_from: 50,
    updated_at: null,
    ...changes,
  }
}
