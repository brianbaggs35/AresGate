import { CircleEllipsis, Cpu, Globe, House, Lock, ShieldHalf, Users, Wrench } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Feed, Listing, Role, Speed } from '@/api/interfaces'
import { formatCount } from '@/format'

/** What a role looks like and means. The sentence is what the owner reads when choosing one, and
 * `outside` says which side of the firewall it is on, which the rest of AresGate reasons from. */
export interface RoleInfo {
  label: string
  icon: NonNullable<IconProps['icon']>
  outside: boolean
  description: string
}

export const ROLE_INFO: Record<Role, RoleInfo> = {
  internet: {
    label: 'Internet',
    icon: Globe,
    outside: true,
    description: 'Where the outside world reaches in: the link to your provider.',
  },
  dmz: {
    label: 'DMZ',
    icon: ShieldHalf,
    outside: true,
    description: 'Servers that are reachable from the internet, kept apart from the rest.',
  },
  home: {
    label: 'Home',
    icon: House,
    outside: false,
    description: 'The network you and your family use: computers, phones, TVs.',
  },
  guest: {
    label: 'Guests',
    icon: Users,
    outside: false,
    description: 'Visitors and anything you do not trust like your own devices.',
  },
  iot: {
    label: 'Smart devices',
    icon: Cpu,
    outside: false,
    description: 'Cameras, plugs, speakers and other things that talk to the internet.',
  },
  vpn: {
    label: 'VPN',
    icon: Lock,
    outside: false,
    description: 'Tunnels in from outside, such as WireGuard or OpenVPN.',
  },
  management: {
    label: 'Management',
    icon: Wrench,
    outside: false,
    description: 'Where the firewall, switches and servers are administered.',
  },
  other: {
    label: 'Other',
    icon: CircleEllipsis,
    outside: false,
    description: 'Anything that does not fit the rest.',
  },
}

export const roleInfo = (role: Role): RoleInfo => ROLE_INFO[role]

/** A feed as a person would name it: where it comes from, and what it is called there. */
export function feedName(feed: Feed): string {
  return feed.native_name
    ? `${feed.integration_name} ${feed.native_name}`
    : `${feed.integration_name}, all of ${feed.connection_label}`
}

/** What the page says first, and how: a sentence, the color of its answer, and how much of the
 * ring is drawn. */
export interface Hero {
  tone: 'primary' | 'success' | 'warning'
  eyebrow: string
  title: string
  detail: string
  mood: 'calm' | 'urgent' | 'idle'
  level: number
}

const plural = (count: number, one: string, many: string) =>
  `${formatCount(count)} ${count === 1 ? one : many}`

export function hero(listing: Listing): Hero {
  const placed = listing.interfaces.reduce((total, item) => total + item.feeds.length, 0)
  const waiting = listing.unplaced.length
  if (waiting > 0) {
    return {
      tone: 'warning',
      eyebrow: 'Needs a decision',
      title: `${plural(waiting, 'feed needs', 'feeds need')} a decision`,
      detail:
        listing.suggestions.length > 0
          ? 'Confirm the suggestions below, or place each feed yourself.'
          : 'Place each feed on the part of your network it belongs to, or set it aside.',
      mood: 'calm',
      level: Math.round((placed / (placed + waiting)) * 100),
    }
  }
  if (listing.interfaces.length > 0) {
    return {
      tone: 'success',
      eyebrow: 'All placed',
      title: `${plural(listing.interfaces.length, 'interface', 'interfaces')}, every feed placed`,
      detail: 'What your programs report is read by the part of the network it belongs to.',
      mood: 'calm',
      level: 100,
    }
  }
  return {
    tone: 'primary',
    eyebrow: 'Nothing found yet',
    title: 'No interfaces yet',
    detail:
      'Find interfaces to see what your programs report, then name the parts of your network they belong to.',
    mood: 'idle',
    level: 0,
  }
}

/** Both directions of a speed added up, a bucket at a time, for one small line. */
export function totalSpeed(speed: Speed): (number | null)[] {
  return speed.received.map((received, index) => {
    const sent = speed.sent[index] ?? null
    return received === null && sent === null ? null : (received ?? 0) + (sent ?? 0)
  })
}

/** The latest bucket that was measured, or null when none was. */
export function latestSpeed(values: readonly (number | null)[]): number | null {
  for (let index = values.length - 1; index >= 0; index--) {
    const value = values[index]
    if (value !== null && value !== undefined) return value
  }
  return null
}
