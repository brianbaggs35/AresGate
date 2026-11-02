import type { Destination, Destinations } from '@/api/alerts'

const NOW = Date.now()
const MINUTE = 60_000

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
  return { items, max_destinations: 10, hosts: ['discord.com', 'discordapp.com'], ...changes }
}
