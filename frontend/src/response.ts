import {
  Ban as BanIcon,
  ShieldBan,
  ShieldCheck,
  ShieldHalf,
  ShieldOff,
  ShieldQuestionMark,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Ban, Incident, IncidentResponse, ResponseState } from '@/api/incidents'
import { formatAgo, formatCount, formatDateTime, formatDuration, formatList } from '@/format'

interface ResponseLook {
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
}

/** What each state looks like. Like a severity, never just a color: each has its icon and name. */
export const RESPONSE: Readonly<Record<ResponseState, ResponseLook>> = {
  banned: { color: 'success', icon: ShieldCheck },
  partly: { color: 'warning', icon: ShieldHalf },
  ban_ended: { color: 'info', icon: ShieldOff },
  blocked: { color: 'info', icon: ShieldBan },
  none: { color: 'secondary', icon: ShieldQuestionMark },
  no_address: { color: 'secondary', icon: BanIcon },
}

/** How often, as it ends a sentence: "once", "14 times". */
export function times(count: number): string {
  return count === 1 ? 'once' : `${formatCount(count)} times`
}

function alerts(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'alert' : 'alerts'}`
}

/** How long is left until a moment, in words: "3h 12m", or "under a minute" within one. */
export function left(iso: string, now: number = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000
  return seconds < 60 ? 'under a minute' : formatDuration(seconds)
}

/** The bans that were meant and still hold, as far as is known. */
function holding(response: IncidentResponse): Ban[] {
  return response.bans.filter((ban) => ban.in_force)
}

/** The latest time any of the bans runs out, or null when none has a time that is known. */
function lastEnd(bans: readonly Ban[]): string | null {
  const ends = bans.flatMap((ban) => (ban.ends_at ? [ban.ends_at] : []))
  return ends.length ? ends.reduce((a, b) => (new Date(a) > new Date(b) ? a : b)) : null
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** What was done about an incident, in a sentence or two. */
export function headline(incident: Incident, now: number = Date.now()): string {
  const done = incident.response
  const bans = holding(done)
  const addresses = [...new Set(bans.map((ban) => ban.address))]
  switch (done.state) {
    case 'no_address':
      return 'This incident names no address, so there is nothing to ban or block.'
    case 'none':
      return 'Nothing has been done about it yet: AresGate has seen no ban and no block.'
    case 'ban_ended': {
      const ended = lastEnd(done.bans.filter((ban) => !ban.simulated && ban.kind === 'ban'))
      return ended
        ? `CrowdSec banned it, and the ban ended ${formatAgo(ended, now)}.`
        : 'CrowdSec banned it, and the ban has ended.'
    }
    case 'blocked': {
      const parts: string[] = []
      if (done.blocked) parts.push(`the firewall turned it away ${times(done.blocked)}`)
      if (done.dropped) parts.push(`Suricata stopped ${alerts(done.dropped)}`)
      return `${capitalised(formatList(parts))}. It was not banned.`
    }
    case 'partly':
      return `CrowdSec banned ${formatCount(addresses.length)} of the ${formatCount(1 + incident.neighbours)} addresses it came from.`
    case 'banned': {
      if (!addresses.length) {
        return 'CrowdSec banned it, but the details of the ban are no longer kept.'
      }
      const who =
        addresses.length === 1 ? (addresses[0] as string) : `${addresses.length} addresses`
      const end = lastEnd(bans)
      const rest = end
        ? `The ban has ${left(end, now)} left.`
        : "How long the ban lasts isn't known."
      return `CrowdSec banned ${who}. ${rest}`
    }
  }
}

/** What a ban is, as a short label for a chip. */
export function banStatus(ban: Ban): string {
  if (ban.simulated) return 'Simulated'
  if (ban.kind !== 'ban') return capitalised(ban.kind)
  return ban.in_force ? 'In force' : 'Ended'
}

/** When a ban ran or runs out, in words. */
export function banEnds(ban: Ban, now: number = Date.now()): string {
  if (ban.simulated) return 'CrowdSec only pretended: it was in its simulation mode.'
  if (ban.kind !== 'ban') return `Not a ban: CrowdSec chose ${ban.kind}.`
  if (!ban.ends_at) return "How long it lasts isn't known."
  return ban.in_force
    ? `Runs out ${formatDateTime(ban.ends_at)}, in ${left(ban.ends_at, now)}.`
    : `Ran out ${formatDateTime(ban.ends_at)}.`
}

/** What a ban was made for and by: the scenario and where it came from, if they are known. */
export function banReason(ban: Ban): string {
  return [ban.scenario, ban.origin].filter(Boolean).join(' · ')
}

/** One thing that happened to the incident's address, for the list of them in order. */
export interface Step {
  key: string
  at: string
  title: string
  detail: string | null
}

/** What happened, in order: the first signal, each ban and its end, and the blocks that came
 * after. The bans are only named by their address when they are not all of the one. */
export function stepsOf(incident: Incident, now: number = Date.now()): Step[] {
  const done = incident.response
  if (done.state === 'no_address') return []
  const bans = done.bans.filter((ban) => !ban.simulated && ban.kind === 'ban')
  const several = new Set(bans.map((ban) => ban.address)).size > 1
  const steps: Step[] = [
    { key: 'first', at: incident.first_seen_at, title: 'First seen', detail: null },
  ]
  bans.forEach((ban, index) => {
    const name = several ? ban.address : null
    steps.push({ key: `ban-${index.toString()}`, at: ban.seen_at, title: 'Banned', detail: name })
    if (ban.ends_at) {
      steps.push({
        key: `end-${index.toString()}`,
        at: ban.ends_at,
        title: new Date(ban.ends_at).getTime() > now ? 'Ban ends' : 'Ban ended',
        detail: name,
      })
    }
  })
  if (done.blocked > 0 && done.last_blocked_at) {
    const since = done.blocked_since_ban ?? 0
    steps.push({
      key: 'blocked',
      at: done.last_blocked_at,
      title: since > 0 ? 'Still trying' : 'Turned away',
      detail:
        since > 0
          ? `The firewall turned it away ${times(since)} after the ban. This was the last.`
          : `The firewall turned it away ${times(done.blocked)}. This was the last.`,
    })
  }
  return steps.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())
}

/** What turned the address away besides a ban, a line to each. */
export function turnedAway(
  response: IncidentResponse,
  now: number = Date.now(),
): { id: string; label: string; value: string }[] {
  const facts: { id: string; label: string; value: string }[] = []
  if (response.blocked > 0) {
    const since = response.blocked_since_ban
    const after = since === null ? '' : ` ${formatCount(since)} of them after the ban.`
    const last = response.last_blocked_at
      ? ` The last was ${formatAgo(response.last_blocked_at, now)}.`
      : ''
    facts.push({
      id: 'firewall',
      label: 'Firewall',
      value: `Turned it away ${times(response.blocked)}.${after}${last}`,
    })
  }
  if (response.dropped > 0) {
    facts.push({
      id: 'suricata',
      label: 'Suricata',
      value: `Stopped ${alerts(response.dropped)}.`,
    })
  }
  return facts
}
