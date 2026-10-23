import type { Collector, CollectorsReport, Worker } from '@/api/collectors'

/** A collector doing well: the connection check on OPNsense, which ran two minutes ago. */
export function collector(changes: Partial<Collector> = {}): Collector {
  const finished = Date.now() - 2 * 60_000
  return {
    collector: 'connection-check',
    title: 'Connection check',
    summary: 'Tests the connection every few minutes.',
    integration: 'opnsense',
    connection: 'api',
    source: 'OPNsense',
    state: 'ok',
    interval_seconds: 300,
    last_started_at: new Date(finished - 1800).toISOString(),
    last_finished_at: new Date(finished).toISOString(),
    last_success_at: new Date(finished).toISOString(),
    last_duration_ms: 1840,
    last_items: null,
    last_error: null,
    consecutive_failures: 0,
    next_run_at: new Date(finished + 300_000).toISOString(),
    ...changes,
  }
}

export function worker(changes: Partial<Worker> = {}): Worker {
  return {
    state: 'running',
    started_at: new Date(Date.now() - 3_600_000).toISOString(),
    seen_at: new Date(Date.now() - 5_000).toISOString(),
    ...changes,
  }
}

export function report(
  collectors: Collector[] = [collector()],
  changes: Partial<Worker> = {},
): CollectorsReport {
  return { worker: worker(changes), collectors }
}
