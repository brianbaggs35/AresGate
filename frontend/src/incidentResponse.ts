import {
  CircleCheck,
  CircleOff,
  Hourglass,
  ShieldAlert,
  ShieldBan,
  ShieldCheck,
  ShieldOff,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type {
  ResponseGroupKey,
  ResponseItem,
  ResponseOverview,
  ResponseRange,
} from '@/api/incidentResponse'
import { formatCount, formatList } from '@/format'
import { left, times } from '@/response'

/** The stretches of time to look back over, shortest first. */
export const RANGES: readonly { key: ResponseRange; label: string; long: string }[] = [
  { key: '24h', label: '24 hours', long: 'the last 24 hours' },
  { key: '7d', label: '7 days', long: 'the last 7 days' },
  { key: '30d', label: '30 days', long: 'the last 30 days' },
]

interface GroupLook {
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
}

/** What each group looks like. Like a severity, never just a color: each has its icon and name. */
export const GROUPS: Readonly<Record<ResponseGroupKey, GroupLook>> = {
  needs_response: { color: 'error', icon: ShieldAlert },
  banned: { color: 'success', icon: ShieldCheck },
  blocked: { color: 'info', icon: ShieldBan },
  ban_ended: { color: 'secondary', icon: ShieldOff },
  closed: { color: 'secondary', icon: CircleCheck },
  no_address: { color: 'secondary', icon: CircleOff },
}

export type ResponseTone = 'urgent' | 'calm' | 'idle'

export interface ResponseHeadline {
  tone: ResponseTone
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** The small word that names the kind of answer, and the sentence. */
  eyebrow: string
  title: string
  detail: string
}

function incidents(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'incident' : 'incidents'}`
}

function count(overview: ResponseOverview, key: ResponseGroupKey): number {
  return overview.groups
    .filter((group) => group.key === key)
    .reduce((sum, group) => sum + group.items.length, 0)
}

/** The answer to the page's question, before anything else: does anything still wait for a
 * response? */
export function headline(overview: ResponseOverview, range: string): ResponseHeadline {
  const waiting = count(overview, 'needs_response')
  if (waiting > 0) {
    return {
      tone: 'urgent',
      color: 'error',
      icon: ShieldAlert,
      eyebrow: 'Needs a response',
      title: `${incidents(waiting)} still ${waiting === 1 ? 'needs' : 'need'} a response`,
      detail: 'They are going on, and nothing has banned them or turned them away.',
    }
  }
  if (overview.shown === 0) {
    return {
      tone: 'idle',
      color: 'info',
      icon: Hourglass,
      eyebrow: 'Quiet',
      title: `No serious incidents in ${range}`,
      detail: `Nothing of ${overview.minimum} severity or higher went on, so there was nothing to respond to.`,
    }
  }
  return {
    tone: 'calm',
    color: 'success',
    icon: CircleCheck,
    eyebrow: 'All answered',
    title: 'Everything that matters has been answered',
    detail: `${incidents(overview.shown)} went on in ${range}, and none of them is waiting for a response.`,
  }
}

/** What to tell the owner when AresGate can't see what CrowdSec or the firewall did, since then
 * "nothing has been done" may only mean that nobody can tell. */
export function coverage(overview: ResponseOverview): string | null {
  const missing = [
    ...(overview.crowdsec_connected ? [] : ['CrowdSec']),
    ...(overview.opnsense_connected ? [] : ['OPNsense']),
  ]
  if (missing.length === 0) return null
  return `${formatList(missing)} ${missing.length === 1 ? "isn't" : "aren't"} connected, so AresGate can't see ${
    missing.length === 2
      ? 'any ban or block'
      : missing[0] === 'CrowdSec'
        ? 'what CrowdSec banned'
        : 'what the firewall or Suricata turned away'
  }. What needs a response may already have been answered.`
}

/** What was done about an incident, in a few words that go on a line of their own. */
export function answer(item: ResponseItem, now: number = Date.now()): string {
  switch (item.state) {
    case 'no_address':
      return 'It names no address, so there is nothing to ban or block.'
    case 'none':
      return 'No ban, and nothing turned it away.'
    case 'ban_ended':
      return 'CrowdSec banned it, and the ban ended.'
    case 'partly':
      return `CrowdSec banned ${formatCount(item.banned_now)} of its ${formatCount(item.attackers)} addresses.`
    case 'blocked': {
      const parts: string[] = []
      if (item.blocked) parts.push(`the firewall turned it away ${times(item.blocked)}`)
      if (item.dropped) {
        parts.push(
          `Suricata stopped ${formatCount(item.dropped)} ${item.dropped === 1 ? 'alert' : 'alerts'}`,
        )
      }
      const said = formatList(parts)
      return `${said.charAt(0).toUpperCase()}${said.slice(1)}.`
    }
    case 'banned': {
      const who = item.banned_now > 1 ? `${formatCount(item.banned_now)} addresses` : 'it'
      return item.ban_ends_at
        ? `CrowdSec banned ${who}, with ${left(item.ban_ends_at, now)} left.`
        : `CrowdSec banned ${who}. How long the ban lasts isn't known.`
    }
  }
}
