import type { Denial, Denials } from '@/api/aiDenials'

export function denial(changes: Partial<Denial> = {}): Denial {
  return {
    id: 1,
    kind: 'status',
    value: 'dismissed',
    incident_id: 12,
    title: 'Scan from 203.0.113.9',
    denied_at: '2026-11-10T10:00:00Z',
    expires_at: '2026-12-10T10:00:00Z',
    ...changes,
  }
}

export function denials(items: Denial[] = [denial()]): Denials {
  return { items, days: 30 }
}
