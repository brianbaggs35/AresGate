import {
  Bug,
  FileText,
  Fingerprint,
  Flag,
  Globe,
  Info,
  Link,
  Search,
  Server,
  User,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type {
  Confirmation,
  Conversation,
  Evidence,
  FlowEnd,
  FlowVolume,
  Named,
  Occurrence,
} from '@/api/incidents'
import { formatBytes, formatCount, formatList } from '@/format'
import { serviceOf } from '@/ports'

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
  cve: { label: 'Known vulnerability', plural: 'Known vulnerabilities', icon: Bug },
  community_id: {
    label: 'Flow ID, to find it in other tools',
    plural: 'Flow IDs, to find them in other tools',
    icon: Fingerprint,
  },
  info: { label: 'What the traffic said', plural: 'What the traffic said', icon: Info },
}

/** What a kind of thing is called, for one that this version doesn't know as it is. */
export function namedLook(kind: string): { label: string; plural: string; icon: Icon } {
  return NAMED[kind] ?? { label: kind, plural: kind, icon: Server }
}

/** The icon for a machine and for an application, which are not named things. */
export { Server as HOST_ICON, AppWindow as APP_ICON } from '@lucide/vue'

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
      evidence.excerpt !== null ||
      evidence.summary !== null ||
      evidence.score !== null ||
      evidence.flow !== null ||
      evidence.payload !== null)
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

/** Where an address is, said in words, for one that no program said anything of. */
export const LOCATION = {
  local: 'On your network',
  remote: 'On the internet',
} as const

const PRIVATE_V4 = [/^10\./, /^192\.168\./, /^172\.(1[6-9]|2\d|3[01])\./, /^169\.254\./, /^127\./]
const PRIVATE_V6 = [/^f[cd][0-9a-f]{2}:/i, /^fe[89ab][0-9a-f]:/i, /^::1$/]

/** Whether an address is one that only your own network uses: a private, link-local or loopback
 * one. */
export function isPrivateAddress(address: string): boolean {
  return [...PRIVATE_V4, ...PRIVATE_V6].some((pattern) => pattern.test(address))
}

/** Where one end of a conversation is: what the program said, or what the address itself says. */
export function locationOf(end: Pick<FlowEnd, 'address' | 'location'>): 'local' | 'remote' {
  if (end.location) return end.location
  return end.address && isPrivateAddress(end.address) ? 'local' : 'remote'
}

/** A country's name in the reader's language, from the two letters a program gives: those letters
 * again where they are not a country's. */
export function countryName(code: string, locale?: string): string {
  try {
    return new Intl.DisplayNames(locale, { type: 'region' }).of(code) ?? code
  } catch {
    return code
  }
}

/** The flag for a country's two letters, or nothing for anything that is not two letters. The flag
 * is a decoration: the country is always named beside it. */
export function flagOf(code: string): string {
  if (!/^[A-Z]{2}$/.test(code)) return ''
  return String.fromCodePoint(
    ...Array.from(code, (letter) => 0x1f1a5 + Number(letter.codePointAt(0))),
  )
}

/** What one end of a conversation is called: its name where a program gave one, or its address. */
export function endTitle(end: Pick<FlowEnd, 'address' | 'name'>): string {
  return end.name ?? end.address ?? 'unknown'
}

/** The service on a conversation's port: what the program called it, or what the port is known
 * for. */
export function serviceFor(end: Pick<FlowEnd, 'service' | 'port'>): string | null {
  return end.service ?? (end.port === null ? null : serviceOf(end.port))
}

/** The port as a line: `53`, or `53 (domain)`. */
export function portLine(end: Pick<FlowEnd, 'service' | 'port'>): string | null {
  if (end.port === null) return null
  const service = serviceFor(end)
  return service ? `${end.port.toString()} (${service})` : end.port.toString()
}

/** What the conversation carried, as one bar of what the client sent and what it got back. */
export function conversationVolume(conversation: Conversation): Volume | null {
  return (
    volumesOf({
      packets_out: null,
      packets_in: null,
      bytes_out: conversation.bytes_out,
      bytes_in: conversation.bytes_in,
    })[0] ?? null
  )
}
