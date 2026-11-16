import { apiDelete, apiGet, apiPatch, apiPost } from '@/api/client'

/** The lists that keep views, which are the ones that can be narrowed and exported. */
export type ViewPage = 'incidents' | 'alerts' | 'devices' | 'assets'

/** What a page's address held: each filter with one value or several. */
export type ViewQuery = Record<string, string | string[]>

/** The filters and the order of a list, kept under a name by the account that saved it. */
export interface SavedView {
  id: number
  page: ViewPage
  name: string
  query: ViewQuery
  is_default: boolean
  created_at: string
  updated_at: string
}

/** Every view this account kept, by page and then by name. */
export async function fetchViews(): Promise<SavedView[]> {
  return (await apiGet<{ items: SavedView[] }>('/views')).items
}

/** Keeps what a list shows under a name. Under a name that is taken, it changes that view. */
export function saveView(
  page: ViewPage,
  name: string,
  query: ViewQuery,
  makeDefault: boolean,
  csrfToken: string,
): Promise<SavedView> {
  return apiPost<SavedView>('/views', { page, name, query, default: makeDefault }, csrfToken)
}

/** Renames a view, or makes it the one its page opens on, or stops it being. */
export function changeView(
  id: number,
  change: { name?: string; default?: boolean },
  csrfToken: string,
): Promise<SavedView> {
  return apiPatch<SavedView>(`/views/${id.toString()}`, change, csrfToken)
}

export function deleteView(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/views/${id.toString()}`, csrfToken)
}
