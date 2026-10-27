import type { KindCount, LogDetail, LogEvent, LogPage, LogSummary, LogVolume } from '@/api/logs'
import type { SourceCount } from '@/api/incidents'
import { SEVERITIES } from '@/severity'

const NOW = Date.now()
const MINUTE = 60_000
const BAR_SECONDS = 300

/** A firewall event from two minutes ago, with whatever is given changed. Its cursor follows
 * from when it happened and its number, as the API's does. */
export function logEvent(changes: Partial<LogEvent> = {}): LogEvent {
  const id = changes.id ?? 1
  const at = changes.at ?? new Date(NOW - 2 * MINUTE).toISOString()
  return {
    cursor: `${(Date.parse(at) * 1000).toString()}.${id.toString()}`,
    id,
    at,
    received_at: at,
    source: 'opnsense',
    source_name: 'OPNsense',
    connection: 'main',
    kind: 'firewall',
    severity: 'medium',
    summary: 'Blocked tcp 93.184.216.34:51514 → 192.168.1.20:22 on WAN',
    signature: null,
    src_address: '93.184.216.34',
    src_port: 51514,
    dst_address: '192.168.1.20',
    dst_port: 22,
    protocol: 'tcp',
    has_raw: true,
    ...changes,
  }
}

/** One event whole, with the record its integration gave and the incident it went into. */
export function logDetail(changes: Partial<LogDetail> = {}): LogDetail {
  return {
    ...logEvent(),
    raw: { action: 'block', interface: 'wan', src: '93.184.216.34', dport: 22, count: 3 },
    incident: {
      id: 7,
      title: 'Brute force on ssh (93.184.216.34)',
      status: 'open',
      severity: 'high',
    },
    ...changes,
  }
}

/** How the events are spread, counted from them: by severity, source and kind, and in bars of
 * five minutes. */
export function logSummary(items: readonly LogEvent[]): LogSummary {
  const severity = { info: 0, low: 0, medium: 0, high: 0, critical: 0 }
  const sources = new Map<string, SourceCount>()
  const kinds = new Map<string, KindCount>()
  for (const item of items) {
    severity[item.severity] += 1
    const source = sources.get(item.source)
    sources.set(item.source, {
      key: item.source,
      name: item.source_name,
      count: (source?.count ?? 0) + 1,
    })
    kinds.set(item.kind, { kind: item.kind, count: (kinds.get(item.kind)?.count ?? 0) + 1 })
  }
  const times = items.map(({ at }) => Date.parse(at))
  const width = BAR_SECONDS * 1000
  const start = Math.floor(Math.min(...times) / width) * width
  const bars = Math.floor((Math.max(...times) - start) / width) + 1
  const counts = Array.from({ length: bars }, () => SEVERITIES.map(() => 0))
  for (const item of items) {
    const bar = Math.floor((Date.parse(item.at) - start) / width)
    const level = SEVERITIES.indexOf(item.severity)
    ;(counts[bar] as number[])[level] = ((counts[bar] as number[])[level] ?? 0) + 1
  }
  const volume: LogVolume | null = items.length
    ? { start: new Date(start).toISOString(), seconds: BAR_SECONDS, counts }
    : null
  return {
    matched: items.length,
    capped: false,
    facets: {
      severity,
      sources: [...sources.values()].sort((a, b) => b.count - a.count),
      kinds: [...kinds.values()].sort((a, b) => b.count - a.count),
    },
    volume,
  }
}

/** A page of events, the newest first, with the summary counted from them unless told. */
export function logPage(items: LogEvent[] = [logEvent()], changes: Partial<LogPage> = {}): LogPage {
  return {
    items,
    more: false,
    terms: [],
    summary: logSummary(items),
    ...changes,
  }
}

/** `count` events a minute apart, the newest first, numbered from `first` down. `skipped` is how
 * many minutes before now the newest of them is, so that a second batch can come after a first. */
export function logEvents(count: number, first = count, skipped = 0): LogEvent[] {
  return Array.from({ length: count }, (_, index) =>
    logEvent({
      id: first - index,
      at: new Date(NOW - (skipped + index + 1) * MINUTE).toISOString(),
      summary: `Blocked connection number ${(first - index).toString()}`,
    }),
  )
}
