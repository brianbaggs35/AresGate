import { apiDelete, apiGet, apiPost } from '@/api/client'

/** The pages that have a search of their own, so a search is kept for the page it was made on. */
export type SearchScope = 'incidents' | 'logs'

/** A search in words, kept under a name. */
export interface SavedSearch {
  id: number
  scope: SearchScope
  name: string
  query: string
  created_at: string
  updated_at: string
}

/** What is kept for a page, by name. */
export async function fetchSavedSearches(scope: SearchScope): Promise<SavedSearch[]> {
  return (await apiGet<{ items: SavedSearch[] }>(`/searches?scope=${scope}`)).items
}

/** Keeps a search under a name. Under a name that is taken, it changes that search. */
export function saveSearch(
  scope: SearchScope,
  name: string,
  query: string,
  csrfToken: string,
): Promise<SavedSearch> {
  return apiPost<SavedSearch>('/searches', { scope, name, query }, csrfToken)
}

export function deleteSavedSearch(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/searches/${id.toString()}`, csrfToken)
}
