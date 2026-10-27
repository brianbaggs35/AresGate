import type { Verdict } from '@/api/verdicts'

const NOW = Date.now()
const HOUR = 3_600_000

/** A verdict that an address is not suspicious, given yesterday and applied to 12 signals, the
 * last of them 2 hours ago, with whatever is given changed. */
export function verdict(changes: Partial<Verdict> = {}): Verdict {
  return {
    id: 1,
    verdict: 'not_suspicious',
    address: '93.184.216.34',
    source: null,
    source_name: null,
    signature: null,
    note: null,
    created_at: new Date(NOW - 24 * HOUR).toISOString(),
    updated_at: new Date(NOW - 24 * HOUR).toISOString(),
    hits: 12,
    last_hit_at: new Date(NOW - 2 * HOUR).toISOString(),
    ...changes,
  }
}
