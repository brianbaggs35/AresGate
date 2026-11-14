import { BellMinus, ShieldAlert, ShieldCheck } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { IncidentDetail, Incident } from '@/api/incidents'
import type { Verdict, VerdictGiven, VerdictKind, VerdictRequest } from '@/api/verdicts'
import { isAboutRule } from '@/incidents'

interface VerdictLook {
  label: string
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** What it means, in a sentence. */
  meaning: string
  /** How a sentence goes on from what it is about: "93.184.216.34 is not suspicious". */
  predicate: string
}

/** What each verdict looks like. Like a severity, never just a color: each has its icon and name. */
export const VERDICT: Readonly<Record<VerdictKind, VerdictLook>> = {
  not_suspicious: {
    label: 'Not suspicious',
    color: 'success',
    icon: ShieldCheck,
    meaning: 'This is normal here. It never raises an alarm, and AresGate learns it from you.',
    predicate: 'is not suspicious',
  },
  low_priority: {
    label: 'Low priority',
    color: 'secondary',
    icon: BellMinus,
    meaning: 'It may be real, but you do not want to hear about it. It never raises an alarm.',
    predicate: 'is low priority',
  },
  threat: {
    label: 'Real threat',
    color: 'error',
    icon: ShieldAlert,
    meaning: 'AresGate is certain of it, whatever else it saw.',
    predicate: 'is a real threat',
  },
}

/** Whether a verdict keeps what it is given of from counting. */
export function isMuting(verdict: VerdictKind): boolean {
  return verdict !== 'threat'
}

/** How many of an incident's signals the verdicts keep from counting. */
export function mutedIn(incident: Pick<Incident, 'verdict_counts'>): number {
  const { not_suspicious: fine = 0, low_priority: low = 0 } = incident.verdict_counts
  return fine + low
}

/** What the verdicts and the noise filters say of an incident, in a sentence for the panel about
 * it. */
export function standing(
  incident: Pick<
    Incident,
    'verdict' | 'verdict_counts' | 'signal_count' | 'filtered_count' | 'cleared_by_ai'
  >,
) {
  const muted = mutedIn(incident)
  const filtered = incident.filtered_count
  if (incident.verdict === 'threat') {
    return 'You said it is a real threat, so AresGate is certain of it.'
  }
  if (incident.verdict !== null && incident.cleared_by_ai !== null) {
    return (
      `The AI was ${incident.cleared_by_ai.confidence.toString()}% sure it is a false positive ` +
      'and gave the verdict itself, so AresGate is sure of nothing and will not raise an alarm ' +
      'for it. Take the verdict back if you disagree.'
    )
  }
  if (incident.verdict !== null) {
    return (
      'Every signal in it matches a verdict you gave, so AresGate is sure of nothing and ' +
      'will not raise an alarm for it.'
    )
  }
  if (filtered > 0 && muted + filtered === incident.signal_count) {
    return (
      'Every signal in it was left out by a verdict you gave or your noise filters, so AresGate ' +
      'is sure of nothing and will not raise an alarm for it.'
    )
  }
  const count = incident.signal_count.toString()
  if (muted > 0 && filtered > 0) {
    return (
      `${muted.toString()} of its ${count} signals match a verdict you gave and ` +
      `${filtered.toString()} were set aside by your noise filters, so none of those are counted.`
    )
  }
  if (muted > 0) {
    return `${muted.toString()} of its ${count} signals match a verdict you gave and are not counted.`
  }
  if (filtered > 0) {
    return `${filtered.toString()} of its ${count} signals were set aside by your noise filters and are not counted.`
  }
  return "You haven't said anything about it yet."
}

type About = Pick<Verdict, 'address' | 'destination' | 'source' | 'source_name' | 'signature'>

/** What a verdict is about, in words: "“ET SCAN” from 93.184.216.34, as seen by Wazuh". */
export function aboutVerdict(about: About): string {
  const program = about.source_name ?? about.source
  const seen = program ? `as seen by ${program}` : null
  if (about.destination) {
    const what = about.signature ? `“${about.signature}”` : 'Traffic'
    const base = `${what} from ${about.address ?? 'any address'} to ${about.destination}`
    return seen ? `${base}, ${seen}` : base
  }
  if (about.signature) {
    const base = `“${about.signature}” from ${about.address ?? 'any address'}`
    return seen ? `${base}, ${seen}` : base
  }
  if (about.address) return program ? `Anything about ${about.address}, ${seen}` : about.address
  return `Everything ${program ?? 'one program'} reports`
}

/** One thing an incident's verdict can be about. */
export interface Scope {
  key: string
  title: string
  /** What it takes in, in a few words. */
  hint: string
  request: Pick<VerdictRequest, 'address' | 'destination' | 'source' | 'signature'>
}

/** How many different alerts an incident offers a verdict on. */
const MAX_ALERTS = 4

/** How many device-to-destination pairs an incident offers a verdict on. */
const MAX_SENT_TO = 2

/** The addresses a home network hands out, where a device's traffic starts: the IPv4 private
 * ranges and the IPv6 unique local ones. */
const INSIDE = /^(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|f[cd][0-9a-f]{2}:)/i

/** The /24 network an IPv4 address is in, where a service's servers are often kept together. An
 * IPv6 address has no such network offered. */
function wholeNetworkOf(address: string): string | null {
  const octets = address.split('.')
  if (address.includes(':') || octets.length !== 4) {
    return null
  }
  return `${octets.slice(0, 3).join('.')}.0/24`
}

/** The pairs of a device inside the network and an address its traffic went to, a few at most. */
function sentTo(signals: IncidentDetail['signals']): { device: string; to: string }[] {
  const pairs = new Map<string, { device: string; to: string }>()
  for (const { src_address: device, dst_address: to } of signals) {
    if (device && to && device !== to && INSIDE.test(device) && pairs.size < MAX_SENT_TO) {
      pairs.set(`${device}\u0000${to}`, { device, to })
    }
  }
  return [...pairs.values()]
}

/** An alert an incident holds, as the program that reported it saw it. */
interface AlertSeen {
  source: string
  name: string
  signature: string
}

/** The alerts an incident offers a verdict on: each signature from each program, a few at most. */
function alertsOf(signals: IncidentDetail['signals']): AlertSeen[] {
  const alerts = new Map<string, AlertSeen>()
  for (const { source, source_name: name, signature } of signals) {
    if (signature && alerts.size < MAX_ALERTS) {
      alerts.set(`${source}\u0000${signature}`, { source, name, signature })
    }
  }
  return [...alerts.values()]
}

/** A verdict on an alert from any address. */
function anyAddressScope({ source, name, signature }: AlertSeen): Scope {
  return {
    key: `alert:${source}:${signature}`,
    title: `“${signature}”`,
    hint: `From any address, as seen by ${name}`,
    request: { source, signature },
  }
}

/** A verdict on an alert from one address alone. */
function thisAddressScope(address: string, { source, name, signature }: AlertSeen): Scope {
  return {
    key: `alert-here:${source}:${signature}`,
    title: `“${signature}” from ${address}`,
    hint: `Only this address, as seen by ${name}`,
    request: { address, source, signature },
  }
}

/** The destinations a device's traffic to an address can be offered as: the address itself, and
 * the whole network it is in where there is one. */
function destinationsOf(to: string): { destination: string; hint: string }[] {
  const network = wholeNetworkOf(to)
  return [
    { destination: to, hint: 'Only what this device sends there' },
    ...(network
      ? [{ destination: network, hint: 'Only what this device sends to the whole network' }]
      : []),
  ]
}

/** A verdict on the traffic a device inside the network sends out, to each address it sends to
 * and to the network of each. */
function sentScopes(signals: IncidentDetail['signals']): Scope[] {
  const scopes: Scope[] = []
  const offered = new Set<string>()
  for (const { device, to } of sentTo(signals)) {
    for (const { destination, hint } of destinationsOf(to)) {
      const key = `sent:${device}>${destination}`
      if (!offered.has(key)) {
        offered.add(key)
        scopes.push({
          key,
          title: `Traffic from ${device} to ${destination}`,
          hint,
          request: { address: device, destination },
        })
      }
    }
  }
  return scopes
}

/** What a verdict on an incident can be about: its address, each alert it holds from any
 * address, and each of them from its address alone, in that order. Then the traffic its devices
 * send out. */
export function scopesOf(incident: Pick<IncidentDetail, 'subject' | 'signals'>): Scope[] {
  const address = isAboutRule(incident.subject) ? null : incident.subject
  const found = alertsOf(incident.signals)
  const scopes: Scope[] = []
  if (address) {
    scopes.push({
      key: 'address',
      title: address,
      hint: 'Everything about this address',
      request: { address },
    })
  }
  scopes.push(...found.map(anyAddressScope))
  if (address) {
    scopes.push(...found.map((alert) => thisAddressScope(address, alert)))
  }
  scopes.push(...sentScopes(incident.signals))
  return scopes
}

/** A verdict given from a list, which the page that shows the list gets to say something of:
 * what it said, what it is about and the verdict as it was kept. */
export interface Judged {
  kind: VerdictKind
  scope: Scope
  rule: VerdictGiven
}

/** What a verdict that was just given reads like afterwards: "Remembered: it is not suspicious." */
export function givenAs(scope: Scope, verdict: VerdictKind): string {
  return `Remembered: ${scope.title} ${VERDICT[verdict].predicate}.`
}

/** The verdicts that were applied to an incident's signals, from all of them. */
export function verdictsIn(
  incident: Pick<IncidentDetail, 'signals'>,
  all: readonly Verdict[],
): Verdict[] {
  const ids = new Set(incident.signals.map(({ verdict_rule_id: id }) => id))
  return all.filter(({ id }) => ids.has(id))
}
