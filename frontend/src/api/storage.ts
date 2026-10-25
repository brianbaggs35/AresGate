import { apiGet, apiPut } from '@/api/client'

/** The two kinds of data that integrations send in and AresGate keeps for a while: what happened
 * (a firewall log line, an alert) and what was measured (a load, a count of bytes). */
export type StorageKind = 'events' | 'metrics'

/** The shortest and longest time anything is kept, in days. The API refuses others. */
export const MIN_DAYS = 1
export const MAX_DAYS = 3650

/** What is kept of one integration's data of one kind. */
export interface StorageSource {
  /** The integration's key, such as `opnsense`. */
  source: string
  name: string
  /** The days set for this integration, or null while it keeps its data for the default. */
  days: number | null
  /** How many days it is kept for, whichever of the two that comes from. */
  effective_days: number
  /** How many events or readings are stored. */
  count: number
  /** When the oldest was made, or null when nothing is stored. */
  oldest_at: string | null
}

export interface Storage {
  default_days: number
  sources: StorageSource[]
}

/** What the API answers with for one integration: the count is named for what it counts. */
interface Answer extends Omit<StorageSource, 'count'> {
  events?: number
  samples?: number
}

function source(kind: StorageKind, { events, samples, ...rest }: Answer): StorageSource {
  return { ...rest, count: (kind === 'events' ? events : samples) as number }
}

const path = (kind: StorageKind, suffix = '') => `/${kind}/storage${suffix}`

/** How much each integration has stored, and for how long it keeps it. */
export async function fetchStorage(kind: StorageKind): Promise<Storage> {
  const answer = await apiGet<{ default_days: number; sources: Answer[] }>(path(kind))
  return {
    default_days: answer.default_days,
    sources: answer.sources.map((item) => source(kind, item)),
  }
}

/** Keeps an integration's data for this many days, or for the default if `days` is null. What is
 * older goes at the next clean-up, which is every few hours. */
export async function setRetention(
  kind: StorageKind,
  key: string,
  days: number | null,
  csrfToken: string,
): Promise<StorageSource> {
  const answer = await apiPut<Answer>(
    path(kind, `/${encodeURIComponent(key)}`),
    { days },
    csrfToken,
  )
  return source(kind, answer)
}
