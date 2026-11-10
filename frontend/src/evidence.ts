import { AppWindow, Bug, FileText, Flag, Globe, Link, Search, Server, User } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Confirmation, Evidence, FlowVolume, Named, Occurrence } from '@/api/incidents'
import { formatBytes, formatCount, formatList } from '@/format'

type Icon = NonNullable<IconProps['icon']>

/** How each kind of thing an alert names is called, and what it looks like. */
export const NAMED: Readonly<Record<string, { label: string; plural: string; icon: Icon }>> = {
  hostname: { label: 'Host name', plural: 'Host names', icon: Globe },
  url: { label: 'Address asked for', plural: 'Addresses asked for', icon: Link },
  user_agent: { label: 'Program it said it was', plural: 'Programs it said it was', icon: Bug },
  dns: { label: 'Name looked up', plural: 'Names looked up', icon: Search },
  sni: { label: 'Site connected to', plural: 'Sites connected to', icon: Globe },
  user: { label: 'User', plural: 'Users', icon: User },
  file: { label: 'File', plural: 'Files', icon: FileText },
  country: { label: 'Country', plural: 'Countries', icon: Flag },
}

/** What a kind of thing is called, for one that this version doesn't know as it is. */
export function namedLook(kind: string): { label: string; plural: string; icon: Icon } {
  return NAMED[kind] ?? { label: kind, plural: kind, icon: Server }
}

/** The icon for a machine and for an application, which are not named things. */
export const HOST_ICON = Server
export const APP_ICON = AppWindow

/** The things an alert named, grouped by kind, in the order the kinds first appear. */
export function namedByKind<T extends Named>(items: readonly T[]): [string, T[]][] {
  const found = new Map<string, T[]>()
  for (const item of items) found.set(item.kind, [...(found.get(item.kind) ?? []), item])
  return [...found]
}

/** How wide to draw a bar for `count` where the largest is `most`, as a whole percent that is
 * never so thin that it isn't seen. */
export function share(count: number, most: number): number {
  return most > 0 ? Math.max(4, Math.round((count / most) * 100)) : 0
}

/** One kind of volume, said as outgoing and incoming with how much of the whole each is. */
export interface Volume {
  label: string
  out: number
  in: number
  outText: string
  inText: string
  /** The outgoing part of the whole, in percent. */
  outShare: number
}

function part(label: string, out: number | null, back: number | null, say: (n: number) => string) {
  if (out === null && back === null) return null
  const sent = out ?? 0
  const received = back ?? 0
  const whole = sent + received
  return {
    label,
    out: sent,
    in: received,
    outText: out === null ? 'not said' : say(out),
    inText: back === null ? 'not said' : say(back),
    outShare: whole > 0 ? Math.round((sent / whole) * 100) : 50,
  } satisfies Volume
}

/** What the flow carried, for each of packets and data that the program counted. */
export function volumesOf(traffic: FlowVolume | null): Volume[] {
  if (!traffic) return []
  return [
    part('Packets', traffic.packets_out, traffic.packets_in, formatCount),
    part('Data', traffic.bytes_out, traffic.bytes_in, formatBytes),
  ].filter((found): found is Volume => found !== null)
}

/** Whether an evidence has anything beyond a machine or an application to show. */
export function hasDetail(evidence: Evidence | null): evidence is Evidence {
  return (
    evidence !== null &&
    (evidence.facts.length > 0 ||
      evidence.tags.length > 0 ||
      evidence.mitre.length > 0 ||
      evidence.named.length > 0 ||
      evidence.traffic !== null ||
      evidence.host !== null ||
      evidence.app !== null ||
      evidence.excerpt !== null)
  )
}

/** The programs that reported an occurrence, the first and those that agreed, with what each
 * said of it. */
export interface Report {
  source: string
  name: string
  evidence: Evidence | null
}

export function reportsOf(occurrence: Occurrence): Report[] {
  return [
    {
      source: occurrence.signal.source,
      name: occurrence.signal.source_name,
      evidence: occurrence.evidence,
    },
    ...occurrence.confirmations.map(({ source, source_name: name, evidence }: Confirmation) => ({
      source,
      name,
      evidence,
    })),
  ]
}

/** Whether an occurrence has anything to say beyond its own line: it was said again, another
 * program said it too, or a program said more. */
export function worthListing(occurrence: Occurrence): boolean {
  return (
    occurrence.count > 1 ||
    occurrence.duplicates > 0 ||
    occurrence.confirmations.length > 0 ||
    hasDetail(occurrence.evidence)
  )
}

/** Which programs also reported an occurrence, in words: `OPNsense and Wazuh`, or "another
 * program" where it is only known that one did. */
export function agreedBy(occurrence: Occurrence): string {
  const names = occurrence.confirmations.map(({ source_name: name }) => name)
  return names.length > 0 ? formatList(names) : 'another program'
}
