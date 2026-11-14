import type {
  ResponseGroup,
  ResponseGroupKey,
  ResponseItem,
  ResponseOverview,
} from '@/api/incidentResponse'

const LABELS: Record<ResponseGroupKey, string> = {
  needs_response: 'Needs a response',
  banned: 'Banned',
  blocked: 'Turned away',
  ban_ended: 'Ban ended',
  closed: 'Closed without a response',
  no_address: 'Nothing to block',
}

export function item(changes: Partial<ResponseItem> = {}): ResponseItem {
  return {
    id: 1,
    title: 'Brute force on ssh (93.184.216.34)',
    subject: '93.184.216.34',
    severity: 'high',
    status: 'open',
    last_seen_at: '2026-11-01T10:00:00Z',
    state: 'none',
    label: 'No response yet',
    why: 'Nothing has banned it or turned it away.',
    banned_now: 0,
    attackers: 1,
    ban_ends_at: null,
    blocked: 0,
    dropped: 0,
    ...changes,
  }
}

/** The overview, with the items given in the groups they name and every other group empty. */
export function overview(
  groups: Partial<Record<ResponseGroupKey, ResponseItem[]>> = {},
  changes: Partial<ResponseOverview> = {},
): ResponseOverview {
  const made: ResponseGroup[] = (Object.keys(LABELS) as ResponseGroupKey[]).map((key) => ({
    key,
    label: LABELS[key],
    description: `${LABELS[key]}, in words.`,
    items: groups[key] ?? [],
  }))
  const shown = made.reduce((sum, group) => sum + group.items.length, 0)
  return {
    days: 7,
    minimum: 'medium',
    total: shown,
    shown,
    crowdsec_connected: true,
    opnsense_connected: true,
    groups: made,
    ...changes,
  }
}
