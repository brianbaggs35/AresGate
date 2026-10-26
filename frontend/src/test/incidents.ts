import type {
  Incident,
  IncidentDetail,
  IncidentDevice,
  IncidentPage,
  Reason,
  Signal,
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
    devices: [device()],
    blocked: 12,
    ...changes,
  }
}

/** A page of incidents, counting each status from the ones in it unless told. */
export function page(items: Incident[] = [incident()], changes: Partial<IncidentPage> = {}) {
  const counts = { open: 0, investigating: 0, resolved: 0, dismissed: 0 }
  for (const { status } of items) counts[status] += 1
  return { total: items.length, items, counts, ...changes } satisfies IncidentPage
}
