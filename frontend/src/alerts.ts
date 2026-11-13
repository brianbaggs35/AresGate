import { Hash, Mail } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { DeliveryReason, DeliveryState, Destination } from '@/api/alerts'
import { formatAgo } from '@/format'

type Icon = NonNullable<IconProps['icon']>

/** How each kind of destination is shown. */
export const KINDS: Readonly<Record<Destination['kind'], { label: string; icon: Icon }>> = {
  discord: { label: 'Discord', icon: Hash },
  email: { label: 'Email', icon: Mail },
}

/** The address of a destination as the page shows it. A webhook's is where it is and the end of
 * its number, and the token as dots, since the token is the secret and is never shown. An email
 * destination's is the address it sends to and the mail server it goes through. */
export function maskedAddress(destination: Destination): string {
  if (destination.kind === 'email') {
    return destination.host
      ? `${destination.recipient ?? ''} through ${destination.host}`
      : `${destination.recipient ?? ''}, once the mail server is set up`
  }
  return `${destination.host}/api/webhooks/${destination.hint}/••••••••`
}

/** What the address is, for someone who can't see how it is set out. */
export function addressLabel(destination: Destination): string {
  return destination.kind === 'email'
    ? 'Email address and the mail server it goes through: '
    : 'Webhook address, with the secret part hidden: '
}

/** What is known about how sending to a destination has gone, in a line. */
export function lastResult(destination: Destination, now: number = Date.now()): string {
  if (destination.status === 'not_connected') {
    return destination.kind === 'email'
      ? "The mail server isn't set up."
      : 'Its webhook address is gone.'
  }
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

/** Where each message is, in the words the log uses, and how it is coloured. */
export const DELIVERY_STATES: Readonly<
  Record<DeliveryState, { label: string; color: string; waiting: boolean }>
> = {
  queued: { label: 'Waiting to be sent', color: 'info', waiting: true },
  held: { label: 'Held for quiet hours', color: 'info', waiting: true },
  retrying: { label: 'Will try again', color: 'warning', waiting: true },
  limited: { label: 'Held back by the limit', color: 'warning', waiting: true },
  summarized: { label: 'Told in a summary', color: 'secondary', waiting: false },
  sent: { label: 'Sent', color: 'success', waiting: false },
  failed: { label: 'Not sent', color: 'error', waiting: false },
  dropped: { label: 'Left out', color: 'secondary', waiting: false },
}

/** Why a message was made. */
export const DELIVERY_REASONS: Readonly<Record<DeliveryReason, string>> = {
  new: 'New incident',
  worse: 'Got worse',
  reopened: 'Reopened',
  limit: 'Summary of what the limit held back',
  quiet: 'Summary of what came in during quiet hours',
  retract: 'Message changed: stood down',
}

/** The log's headline: how many were sent, how many wait and how many did not get through. */
export function deliveryTotals(counts: Partial<Record<DeliveryState, number>>): string {
  const of = (...states: DeliveryState[]) =>
    states.reduce((total, state) => total + (counts[state] ?? 0), 0)
  const sent = of('sent')
  const waiting = of('queued', 'held', 'retrying', 'limited')
  const failed = of('failed')
  if (sent + waiting + failed + of('summarized', 'dropped') === 0) return 'Nothing yet.'
  return [
    `${sent.toString()} sent`,
    `${waiting.toString()} waiting`,
    `${failed.toString()} not sent`,
  ].join(', ')
}

/** What a summary is called in the log, since it has no incident of its own. */
export function deliveryTitle(delivery: {
  kind: 'incident' | 'summary' | 'update'
  title: string
  covers: number
  reason: DeliveryReason
}): string {
  if (delivery.kind === 'incident') return delivery.title
  if (delivery.kind === 'update') return `Stood down: ${delivery.title}`
  const many = `${delivery.covers.toString()} ${delivery.covers === 1 ? 'incident' : 'incidents'}`
  return delivery.reason === 'quiet'
    ? `${many} came in during quiet hours`
    : `${many} held back by the limit`
}
