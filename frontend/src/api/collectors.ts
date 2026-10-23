import { apiGet } from '@/api/client'

/** How a collector is doing: it has not finished a run yet, it works, its last run failed, or
 * it should have run by now and has not (which is what a stopped worker looks like). */
export type CollectorState = 'waiting' | 'ok' | 'problem' | 'late'

/** How the worker that runs the collectors is doing. */
export type WorkerState = 'running' | 'stopped' | 'unknown' | 'off'

/** One job that reads from one connection of an integration, such as the connection check. */
export interface Collector {
  collector: string
  title: string
  /** One sentence on what it does. */
  summary: string
  integration: string
  connection: string
  /** Where it reads from: the integration's name, and the connection's if it has several. */
  source: string
  state: CollectorState
  interval_seconds: number
  last_started_at: string | null
  last_finished_at: string | null
  last_success_at: string | null
  last_duration_ms: number | null
  /** How many things the last run that worked collected, for a collector that counts them. */
  last_items: number | null
  last_error: string | null
  consecutive_failures: number
  next_run_at: string | null
}

export interface Worker {
  state: WorkerState
  /** When this run of the worker began, and when it last said it was alive. */
  started_at: string | null
  seen_at: string | null
}

export interface CollectorsReport {
  worker: Worker
  collectors: Collector[]
}

/** The worker and its collectors, or only those of one integration. */
export function fetchCollectors(integration?: string): Promise<CollectorsReport> {
  const suffix = integration === undefined ? '' : `?integration=${encodeURIComponent(integration)}`
  return apiGet<CollectorsReport>(`/collectors${suffix}`)
}
