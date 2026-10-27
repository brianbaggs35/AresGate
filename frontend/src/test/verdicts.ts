import type { Verdict, VerdictGiven, VerdictKind } from '@/api/verdicts'
import type { Judged } from '@/verdicts'

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

/** The answer to giving a verdict: a new one, unless it says what it replaced. */
export function given(changes: Partial<VerdictGiven> = {}): VerdictGiven {
  return { ...verdict(), replaced: null, ...changes }
}

/** What a card says when it has given a verdict of not suspicious on an address. */
export function judged(changes: Partial<{ kind: VerdictKind; rule: VerdictGiven }> = {}): Judged {
  return {
    kind: 'not_suspicious',
    scope: {
      key: 'address',
      title: '93.184.216.34',
      hint: 'everything from it',
      request: { address: '93.184.216.34' },
    },
    rule: given(),
    ...changes,
  }
}
