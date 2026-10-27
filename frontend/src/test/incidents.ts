import type {
  BulkResult,
  Incident,
  IncidentDetail,
  IncidentDevice,
  IncidentPage,
  Reason,
  Signal,
  SourceCount,
} from '@/api/incidents'

const NOW = Date.now()
const MINUTE = 60_000

/** An incident that is open and quite sure: an attack on ssh that Wazuh and OPNsense both saw,
 * 20 minutes ago, with whatever is given changed. */
export function incident(changes: Partial<Incident> = {}): Incident {
  return {
    id: 1,
    title: 'Brute force on ssh (93.184.216.34)',
    subject: '93.184.216.34',
    severity: 'high',
    confidence: 70,
    confidence_level: 'high',
    status: 'open',
    first_seen_at: new Date(NOW - 20 * MINUTE).toISOString(),
    last_seen_at: new Date(NOW - 2 * MINUTE).toISOString(),
    signal_count: 3,
    sources: [
      { key: 'opnsense', name: 'OPNsense' },
      { key: 'wazuh', name: 'Wazuh' },
    ],
    addresses: ['93.184.216.34', '192.168.1.20'],
    banned: false,
    status_changed_at: null,
    verdict: null,
    verdict_counts: {},
    activities: [],
    waves: 1,
    port_count: 0,
    ports_capped: false,
    neighbours: 0,
    ...changes,
  }
}

export function reason(changes: Partial<Reason> = {}): Reason {
  return {
    rule: 'strongest',
    points: 40,
    text: 'The most serious signal is rated high by Wazuh: Brute force on ssh',
    ...changes,
  }
}

export function signal(changes: Partial<Signal> = {}): Signal {
  return {
    occurred_at: new Date(NOW - 20 * MINUTE).toISOString(),
    source: 'wazuh',
    source_name: 'Wazuh',
    kind: 'alert',
    severity: 'high',
    summary: 'sshd: authentication failed',
    signature: 'Brute force on ssh',
    src_address: '93.184.216.34',
    src_port: 51514,
    dst_address: '192.168.1.20',
    dst_port: 22,
    protocol: 'tcp',
    verdict: null,
    verdict_rule_id: null,
    ...changes,
  }
}

export function device(changes: Partial<IncidentDevice> = {}): IncidentDevice {
  return {
    id: 4,
    address: '192.168.1.20',
    mac: 'aa:bb:cc:00:11:22',
    hostname: 'nas',
    vendor: 'Synology',
    ...changes,
  }
}

/** One incident with all it knows: why it is as sure as it is, its signals and its devices. */
export function detail(changes: Partial<IncidentDetail> = {}): IncidentDetail {
  return {
    ...incident(),
    reasons: [
      reason(),
      reason({
        rule: 'corroborated',
        points: 15,
        text: '2 programs saw it: OPNsense and Wazuh.',
      }),
      reason({ rule: 'repeated', points: 10, text: 'It has set off 5 signals.' }),
    ],
    signals: [
      signal(),
      signal({
        occurred_at: new Date(NOW - 12 * MINUTE).toISOString(),
        source: 'opnsense',
        source_name: 'OPNsense',
        severity: 'medium',
        summary: 'ET SCAN Potential SSH Scan',
        signature: 'ET SCAN Potential SSH Scan',
        src_port: null,
      }),
      signal({
        occurred_at: new Date(NOW - 2 * MINUTE).toISOString(),
        severity: 'low',
        summary: 'Failed password for root',
        signature: null,
        src_port: null,
        dst_address: null,
        dst_port: null,
        protocol: null,
      }),
    ],
    grouping: [
      'Everything in it is about 93.184.216.34, whichever program saw it.',
      'Each brute force signal came less than 6 hours after the one before it. A longer quiet, or more than 24 hours in all, starts another incident.',
    ],
    ports: [22],
    devices: [device()],
    blocked: 12,
    ...changes,
  }
}

/** A page of incidents, counting each status, severity and source from the ones in it unless
 * told. */
export function page(items: Incident[] = [incident()], changes: Partial<IncidentPage> = {}) {
  const counts = { open: 0, investigating: 0, resolved: 0, dismissed: 0 }
  const severity = { info: 0, low: 0, medium: 0, high: 0, critical: 0 }
  const sources = new Map<string, SourceCount>()
  for (const item of items) {
    counts[item.status] += 1
    severity[item.severity] += 1
    for (const { key, name } of item.sources) {
      sources.set(key, { key, name, count: (sources.get(key)?.count ?? 0) + 1 })
    }
  }
  return {
    total: items.length,
    items,
    terms: [],
    facets: { severity, sources: [...sources.values()].sort((a, b) => b.count - a.count) },
    counts,
    quieted: 0,
    ...changes,
  } satisfies IncidentPage
}

/** What a change to many incidents says it did: two incidents, both changed, nothing to undo. */
export function bulkResult(changes: Partial<BulkResult> = {}): BulkResult {
  return {
    preview: false,
    incidents: 2,
    signals: 5,
    changed: 2,
    skipped: 0,
    verdicts: 0,
    undo: null,
    ...changes,
  }
}
