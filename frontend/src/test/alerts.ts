import type { Choices, Destination, Destinations, Rules, RulesPreview } from '@/api/alerts'

const NOW = Date.now()
const MINUTE = 60_000

/** What a new destination is told about: what is serious and what AresGate is sure of. */
export function rules(changes: Partial<Rules> = {}): Rules {
  return {
    min_severity: 2,
    min_confidence: 65,
    sources: [],
    activities: [],
    quiet_hours: false,
    quiet_from: 22 * 60,
    quiet_until: 7 * 60,
    quiet_critical: true,
    time_zone: 'UTC',
    max_per_hour: 6,
    detail: 'standard',
    again_when_worse: true,
    ...changes,
  }
}

/** What the rules can name. */
export function choices(): Choices {
  return {
    sources: [
      { key: 'opnsense', name: 'OPNsense' },
      { key: 'ntopng', name: 'ntopng' },
      { key: 'wazuh', name: 'Wazuh' },
    ],
    activities: [
      { key: 'scan', name: 'scanning' },
      { key: 'brute_force', name: 'brute force' },
    ],
  }
}

/** What the rules of a new destination would have done in the last day: two incidents sent, and
 * three left out for two reasons. */
export function preview(changes: Partial<RulesPreview> = {}): RulesPreview {
  return {
    hours: 24,
    considered: 5,
    would_send: 2,
    held: 0,
    busiest_hour: 2,
    over_limit: 0,
    truncated: false,
    left_out: [
      { reason: 'confidence', text: 'AresGate is less than 65% sure', count: 2 },
      { reason: 'muted', text: 'You called it not suspicious or low priority', count: 1 },
    ],
    examples: [
      {
        id: 12,
        title: 'Port scan from 203.0.113.7',
        severity: 'high',
        confidence: 82,
        last_seen_at: new Date(NOW - 20 * MINUTE).toISOString(),
      },
      {
        id: 9,
        title: 'SSH brute force from 198.51.100.4',
        severity: 'critical',
        confidence: 91,
        last_seen_at: new Date(NOW - 90 * MINUTE).toISOString(),
      },
    ],
    ...changes,
  }
}

/** A Discord destination that has never been tried, with whatever is given changed. */
export function destination(changes: Partial<Destination> = {}): Destination {
  return {
    id: 1,
    kind: 'discord',
    name: 'Security channel',
    enabled: true,
    host: 'discord.com',
    hint: '…6789',
    status: 'untested',
    last_attempt_at: null,
    last_success_at: null,
    last_error: null,
    rules: rules(),
    created_at: new Date(NOW - 60 * MINUTE).toISOString(),
    updated_at: new Date(NOW - 60 * MINUTE).toISOString(),
    ...changes,
  }
}

/** A destination whose last message got through, ten minutes ago. */
export function working(changes: Partial<Destination> = {}): Destination {
  const at = new Date(NOW - 10 * MINUTE).toISOString()
  return destination({
    status: 'connected',
    last_attempt_at: at,
    last_success_at: at,
    ...changes,
  })
}

/** A destination whose last try failed, five minutes ago, after one that worked an hour before. */
export function failing(changes: Partial<Destination> = {}): Destination {
  return destination({
    status: 'problem',
    last_attempt_at: new Date(NOW - 5 * MINUTE).toISOString(),
    last_success_at: new Date(NOW - 60 * MINUTE).toISOString(),
    last_error: "Discord doesn't accept this webhook (HTTP 404).",
    ...changes,
  })
}

export function destinations(
  items: Destination[] = [],
  changes: Partial<Destinations> = {},
): Destinations {
  return {
    items,
    max_destinations: 10,
    hosts: ['discord.com', 'discordapp.com'],
    choices: choices(),
    ...changes,
  }
}
