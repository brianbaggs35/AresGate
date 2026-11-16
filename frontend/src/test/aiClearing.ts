import type { Clearing, ClearingPreview } from '@/api/aiClearing'

/** The settings as they are before the owner saves any. */
export function clearing(changes: Partial<Clearing> = {}): Clearing {
  return {
    mode: 'suggest',
    minimum: 80,
    kinds: ['noise', 'probe', 'unclear'],
    sources: [],
    ceiling: 'medium',
    daily_cap: 25,
    aggressiveness: 'balanced',
    presets: [
      { key: 'careful', minimum: 90, summary: 'Clears only what it is nearly certain of.' },
      { key: 'balanced', minimum: 80, summary: 'Clears what it is quite sure of.' },
      { key: 'thorough', minimum: 65, summary: 'Clears what is probably nothing.' },
    ],
    available_sources: [
      { key: 'ntopng', name: 'ntopng' },
      { key: 'wazuh', name: 'Wazuh' },
    ],
    min_minimum: 50,
    max_minimum: 99,
    max_cap: 500,
    cleared_today: 0,
    held: null,
    updated_at: null,
    ...changes,
  }
}

export function clearingPreview(changes: Partial<ClearingPreview> = {}): ClearingPreview {
  return { days: 7, read: 12, would_clear: 4, ...changes }
}
