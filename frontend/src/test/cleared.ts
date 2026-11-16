import type { ClearedItem, ClearedPage } from '@/api/aiCleared'

const NOW = Date.parse('2026-06-01T12:00:00Z')

/** A suggestion waiting for the owner: the AI read a scan of ssh as nothing. */
export function clearedItem(changes: Partial<ClearedItem> = {}): ClearedItem {
  return {
    kind: 'waiting',
    id: 4,
    incident: {
      id: 4,
      title: 'ET SCAN Potential SSH Scan from 93.184.216.34',
      severity: 'medium',
      status: 'open',
      subject: '93.184.216.34',
      last_seen_at: new Date(NOW - 600_000).toISOString(),
    },
    verdict: 'not_suspicious',
    reason: 'It is the scanner the owner runs.',
    confidence: 91,
    classification: 'noise',
    provider: 'Anthropic',
    model: 'claude-haiku-5-5',
    at: new Date(NOW - 3_600_000).toISOString(),
    story: 'It tried a port and went away.',
    checks: ['The address is a known research scanner.'],
    observations: ['Three connection attempts to port 22.'],
    ...changes,
  }
}

/** A page of the lists of what the AI cleared. */
export function clearedPage(changes: Partial<ClearedPage> = {}): ClearedPage {
  return {
    state: 'waiting',
    counts: { waiting: 1, cleared: 2 },
    total: 1,
    items: [clearedItem()],
    mode: 'suggest',
    held: null,
    ...changes,
  }
}
