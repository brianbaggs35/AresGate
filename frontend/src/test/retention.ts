import type { RetentionSettings } from '@/api/retentionSettings'

/** The retention settings of a new install: not managed, so everything is as it was. */
export function retentionSettings(changes: Partial<RetentionSettings> = {}): RetentionSettings {
  return {
    managed: false,
    keep_forever: false,
    days: 30,
    quota_gb: null,
    default_days: 30,
    min_days: 1,
    max_days: 3650,
    min_quota_gb: 1,
    max_quota_gb: 100000,
    built_in: { events: 30, metrics: 30, api_log: 30, ai_log: 90, alert_log: 30, audit: 365 },
    usage: {
      database_bytes: 2_147_483_648,
      events_bytes: 1_073_741_824,
      metrics_bytes: 268_435_456,
      oldest_event_at: '2026-10-20T08:00:00Z',
      quota_bytes: null,
      over_quota: false,
    },
    updated_at: null,
    ...changes,
  }
}
