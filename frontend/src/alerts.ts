import { Hash } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Destination } from '@/api/alerts'
import { formatAgo } from '@/format'

type Icon = NonNullable<IconProps['icon']>

/** How each kind of destination is shown. Discord's webhooks are the first. */
export const KINDS: Readonly<Record<Destination['kind'], { label: string; icon: Icon }>> = {
  discord: { label: 'Discord', icon: Hash },
}

/** The address of a destination as the page shows it: where it is and the end of its number, and
 * the token as dots, since the token is the secret and is never shown. */
export function maskedAddress(destination: Destination): string {
  return `${destination.host}/api/webhooks/${destination.hint}/••••••••`
}

/** What is known about how sending to a destination has gone, in a line. */
export function lastResult(destination: Destination, now: number = Date.now()): string {
  if (destination.status === 'not_connected') return 'Its webhook address is gone.'
  if (destination.last_attempt_at === null) {
    return 'Not tried yet. Send a test message to check it.'
  }
  if (destination.last_error !== null) {
    return destination.last_success_at
      ? `The last try failed. A message last got through ${formatAgo(destination.last_success_at, now)}.`
      : 'The last try failed. No message has got through yet.'
  }
  return `A message last got through ${formatAgo(destination.last_success_at ?? destination.last_attempt_at, now)}.`
}
