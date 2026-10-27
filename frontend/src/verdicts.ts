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

/** What the verdicts say of an incident, in a sentence for the panel about it. */
export function standing(incident: Pick<Incident, 'verdict' | 'verdict_counts' | 'signal_count'>) {
  const muted = mutedIn(incident)
  if (incident.verdict === 'threat') {
    return 'You said it is a real threat, so AresGate is certain of it.'
  }
  if (incident.verdict !== null) {
    return (
      'Every signal in it matches a verdict you gave, so AresGate is sure of nothing and ' +
      'will not raise an alarm for it.'
    )
  }
  if (muted > 0) {
    const count = incident.signal_count.toString()
    return `${muted.toString()} of its ${count} signals match a verdict you gave and are not counted.`
  }
  return "You haven't said anything about it yet."
}

type About = Pick<Verdict, 'address' | 'source' | 'source_name' | 'signature'>

/** What a verdict is about, in words: "“ET SCAN” from 93.184.216.34, as seen by Wazuh". */
export function aboutVerdict(about: About): string {
  const program = about.source_name ?? about.source
  const seen = program ? `as seen by ${program}` : null
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
  request: Pick<VerdictRequest, 'address' | 'source' | 'signature'>
}

/** How many different alerts an incident offers a verdict on. */
const MAX_ALERTS = 4

/** What a verdict on an incident can be about: its address, each alert it holds from any
 * address, and each of them from its address alone, in that order. */
export function scopesOf(incident: Pick<IncidentDetail, 'subject' | 'signals'>): Scope[] {
  const address = isAboutRule(incident.subject) ? null : incident.subject
  const alerts = new Map<string, { source: string; name: string; signature: string }>()
  for (const { source, source_name: name, signature } of incident.signals) {
    if (signature && alerts.size < MAX_ALERTS) {
      alerts.set(`${source}\u0000${signature}`, { source, name, signature })
    }
  }
  const found = [...alerts.values()]
  const scopes: Scope[] = []
  if (address) {
    scopes.push({
      key: 'address',
      title: address,
      hint: 'Everything about this address',
      request: { address },
    })
  }
  for (const { source, name, signature } of found) {
    scopes.push({
      key: `alert:${source}:${signature}`,
      title: `“${signature}”`,
      hint: `From any address, as seen by ${name}`,
      request: { source, signature },
    })
  }
  if (address) {
    for (const { source, name, signature } of found) {
      scopes.push({
        key: `alert-here:${source}:${signature}`,
        title: `“${signature}” from ${address}`,
        hint: `Only this address, as seen by ${name}`,
        request: { address, source, signature },
      })
    }
  }
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
