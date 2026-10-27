import type { SavedSearch } from '@/api/searches'

/** A search kept for the logs, saved an hour ago, with whatever is given changed. */
export function saved(changes: Partial<SavedSearch> = {}): SavedSearch {
  const at = new Date(Date.now() - 3_600_000).toISOString()
  return {
    id: 1,
    scope: 'logs',
    name: 'Scans',
    query: 'kind:alert since:6h',
    created_at: at,
    updated_at: at,
    ...changes,
  }
}
