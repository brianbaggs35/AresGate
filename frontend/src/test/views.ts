import type { SavedView } from '@/api/views'

/** A view of the incidents kept an hour ago, with whatever is given changed. */
export function kept(changes: Partial<SavedView> = {}): SavedView {
  const at = new Date(Date.now() - 3_600_000).toISOString()
  return {
    id: 1,
    page: 'incidents',
    name: 'Needs a look',
    query: { view: 'all', severity: 'high' },
    is_default: false,
    created_at: at,
    updated_at: at,
    ...changes,
  }
}
