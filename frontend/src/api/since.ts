import { apiGet, apiPost } from '@/api/client'
import type { Severity } from '@/severity'

/** What is new since this account last looked at the dashboard. */
export interface Since {
  /** When it last looked, or null on a first visit, which has nothing to compare with. */
  since: string | null
  /** The incidents that began since, by how serious, as the incident list shows them. */
  incidents: Record<Severity, number>
  cleared_by_ai: number
  new_devices: number
  /** How many things there are in all. */
  total: number
}

export function fetchSince(): Promise<Since> {
  return apiGet<Since>('/dashboard/since')
}

/** Says the account has now looked, so the next visit is compared with this one. */
export function markSeen(csrfToken: string): Promise<undefined> {
  return apiPost<undefined>('/dashboard/seen', undefined, csrfToken)
}
