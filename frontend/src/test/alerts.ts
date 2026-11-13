import type {
  Choices,
  Deliveries,
  Delivery,
  Destination,
  Destinations,
  DiscordMessage,
  MailServer,
  Rules,
  RulesPreview,
  Sample,
} from '@/api/alerts'

const NOW = Date.now()
const MINUTE = 60_000

/** The rules of a destination told of what is serious and what AresGate is sure of. (The server
 * makes a new one told of threats only; that is `threatRules()`.) */
export function rules(changes: Partial<Rules> = {}): Rules {
  return {
    mode: 'custom',
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

/** The rules of a destination told of real attacks only, as the server makes a new one. */
export function threatRules(changes: Partial<Rules> = {}): Rules {
  return rules({ mode: 'threats', ...changes })
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
    recipient: null,
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

/** An email destination, through a mail server that is set up. */
export function emailDestination(changes: Partial<Destination> = {}): Destination {
  return destination({
    id: 2,
    kind: 'email',
    name: 'Inbox',
    host: 'smtp.example.com',
    hint: '',
    recipient: 'me@example.org',
    ...changes,
  })
}

/** The mail server as it is before it is set up. */
export function noMailServer(changes: Partial<MailServer> = {}): MailServer {
  return {
    configured: false,
    host: '',
    port: 587,
    security: 'starttls',
    username: null,
    sender: '',
    password_kept: false,
    default_ports: { starttls: 587, ssl: 465, none: 25 },
    ...changes,
  }
}

/** A mail server that is set up, with a password kept. */
export function mailServer(changes: Partial<MailServer> = {}): MailServer {
  return noMailServer({
    configured: true,
    host: 'smtp.example.com',
    username: 'alerts@example.com',
    sender: 'alerts@example.com',
    password_kept: true,
    ...changes,
  })
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
    smtp: noMailServer(),
    max_destinations: 10,
    hosts: ['discord.com', 'discordapp.com'],
    choices: choices(),
    ...changes,
  }
}

/** A message that was sent a few minutes ago, with whatever is given changed. */
export function delivery(changes: Partial<Delivery> = {}): Delivery {
  return {
    id: 1,
    destination_id: 1,
    destination: 'Security channel',
    incident_id: 12,
    kind: 'incident',
    reason: 'new',
    state: 'sent',
    title: 'Port scan from 203.0.113.7',
    severity: 'high',
    confidence: 82,
    covers: 0,
    attempts: 1,
    created_at: new Date(NOW - 6 * MINUTE).toISOString(),
    due_at: new Date(NOW - 6 * MINUTE).toISOString(),
    sent_at: new Date(NOW - 5 * MINUTE).toISOString(),
    note: null,
    ...changes,
  }
}

/** A page of the log. */
export function deliveries(
  items: Delivery[] = [delivery()],
  changes: Partial<Deliveries> = {},
): Deliveries {
  return { items, next_before: null, counts: { sent: items.length }, ...changes }
}

/** A message about a threat as the server makes a sample of it. */
export function sample(changes: Partial<DiscordMessage['embeds'][number]> = {}): Sample {
  return {
    payload: {
      username: 'AresGate',
      embeds: [
        {
          title: 'Attack in progress: High-severity scanning from 93.184.216.34',
          description: [
            'AresGate is 88% sure this is a real attack, and it is going on now.',
            '',
            '**Why AresGate thinks so**',
            '• It is more than scanning: it went through 2 stages (recon then access).',
            '',
            '[Open the incident](https://aresgate.example/incidents) to see what was seen and why.',
          ].join('\n'),
          color: 0xef4444,
          url: 'https://aresgate.example/incidents',
          footer: { text: 'AresGate · sample alert' },
          fields: [
            {
              name: 'How far it got',
              value: 'Looking around → **Trying to get in**',
              inline: false,
            },
            { name: 'How sure', value: '88%', inline: true },
            { name: 'Seen from', value: '`93.184.216.34`', inline: true },
          ],
          ...changes,
        },
      ],
    },
  }
}
