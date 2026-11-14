import { apiGet, apiPut } from '@/api/client'

/** What is changed when saving, which is all of it. */
export interface RetentionDraft {
  /** Whether the choices below are used at all. Off leaves everything as it was. */
  managed: boolean
  /** Keep everything, however old: no age limit and no quota. */
  keep_forever: boolean
  /** How many days data is kept. */
  days: number
  /** The most the database may hold, in gigabytes, or null for no limit. */
  quota_gb: number | null
}

/** How long each kind of data is kept while retention is not managed on the page. */
export interface BuiltInPeriods {
  events: number
  metrics: number
  api_log: number
  ai_log: number
  alert_log: number
  audit: number
}

/** How much the database holds, and how much of that is events and measurements. */
export interface RetentionUsage {
  database_bytes: number
  events_bytes: number
  metrics_bytes: number
  oldest_event_at: string | null
  /** The quota in bytes while one is in force. */
  quota_bytes: number | null
  over_quota: boolean
}

export interface RetentionSettings extends RetentionDraft {
  default_days: number
  min_days: number
  max_days: number
  min_quota_gb: number
  max_quota_gb: number
  built_in: BuiltInPeriods
  usage: RetentionUsage
  updated_at: string | null
}

export function fetchRetentionSettings(): Promise<RetentionSettings> {
  return apiGet<RetentionSettings>('/retention-settings')
}

export function saveRetentionSettings(
  draft: RetentionDraft,
  csrfToken: string,
): Promise<RetentionSettings> {
  return apiPut<RetentionSettings>('/retention-settings', draft, csrfToken)
}
