import { ShieldCheck, ShieldQuestionMark } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Trust, TrustLevel, TrustRequest } from '@/api/trust'

export interface LevelLook {
  label: string
  meaning: string
  icon: NonNullable<IconProps['icon']>
  color: string
}

/** How much to trust something, in words, with the icon and color of each so that the color is
 * never the only thing that says it. */
export const LEVEL: Readonly<Record<TrustLevel, LevelLook>> = {
  not_suspicious: {
    label: 'Safe',
    meaning: 'It is fine. It never raises an alarm and adds nothing to how sure AresGate is.',
    icon: ShieldCheck,
    color: 'success',
  },
  low_priority: {
    label: 'Low priority',
    meaning: 'It is worth a glance, not an alarm. It is kept in the timeline and never alarms.',
    icon: ShieldQuestionMark,
    color: 'info',
  },
}

export const LEVELS: readonly TrustLevel[] = ['not_suspicious', 'low_priority']

/** One way of saying what to trust about an address, from the narrowest to the widest. */
export interface Scope {
  key: string
  label: string
  detail: string
  request: TrustRequest
}

/** What can be trusted about what is on the screen: an address on the internet, and where
 * it is known the device that talked to it and the alert's signature. The narrowest comes
 * first, so the safest choice is the one that is ready. */
export function scopesFor(about: {
  address: string
  /** The device on your network that sent to it: its address, and what it is called. */
  device?: { address: string; name?: string | null } | null
  signature?: string | null
}): Scope[] {
  const scopes: Scope[] = []
  if (about.device) {
    const name = about.device.name || about.device.address
    scopes.push({
      key: 'traffic',
      label: `Only what ${name} sends to ${about.address}`,
      detail: `That device's traffic to this address. An attack aimed at ${name}, and anything else it does, still counts.`,
      request: { address: about.device.address, destination: about.address },
    })
  }
  if (about.signature) {
    scopes.push({
      key: 'alert',
      label: `Only the alert “${about.signature}” about ${about.address}`,
      detail: 'That one kind of alert. Other alerts about the address still count.',
      request: { address: about.address, signature: about.signature },
    })
  }
  scopes.push({
    key: 'address',
    label: `Everything about ${about.address}`,
    detail: `Every alert about it or from it, from every program. An attack on a device from this address no longer counts.`,
    request: { address: about.address },
  })
  return scopes
}

/** What a decision says it applied to, in words. */
export function appliedText(rule: Pick<Trust, 'hits' | 'incidents'>): string {
  if (rule.hits === 0) return 'Not applied to anything yet'
  const signals = `${rule.hits.toString()} ${rule.hits === 1 ? 'alert' : 'alerts'}`
  const incidents = `${rule.incidents.toString()} ${rule.incidents === 1 ? 'incident' : 'incidents'}`
  return `Kept ${signals} in ${incidents} from raising an alarm`
}

/** The programs whose alerts a decision can be limited to. */
export const SOURCES: readonly { value: string; title: string }[] = [
  { value: 'opnsense', title: 'OPNsense' },
  { value: 'ntopng', title: 'ntopng' },
  { value: 'wazuh', title: 'Wazuh' },
  { value: 'crowdsec', title: 'CrowdSec' },
]

/** What a form of a decision holds, as the text that was typed. */
export interface TrustFields {
  verdict: TrustLevel
  address: string
  destination: string
  source: string
  signature: string
  note: string
}

export function fieldsOf(rule: Trust | null): TrustFields {
  return {
    verdict: rule?.verdict ?? 'not_suspicious',
    address: rule?.address ?? '',
    destination: rule?.destination ?? '',
    source: rule?.source ?? '',
    signature: rule?.signature ?? '',
    note: rule?.note ?? '',
  }
}

/** What to send for what was typed: what is empty is left out, and a note that is cleared is
 * sent as empty, which takes it off. */
export function requestOf(fields: TrustFields): TrustRequest {
  const request: TrustRequest = { verdict: fields.verdict, note: fields.note.trim() }
  for (const key of ['address', 'destination', 'source', 'signature'] as const) {
    const text = fields[key].trim()
    if (text) request[key] = text
  }
  return request
}

/** What is wrong with what was typed, in words, or null. */
export function problemWith(fields: TrustFields): string | null {
  const named = [fields.address, fields.source, fields.signature].some((text) => text.trim())
  if (!named) return 'Say what to trust: an address, a program or an alert.'
  if (fields.destination.trim() && !fields.address.trim()) {
    return 'A destination is where an address sends to, so name that address too.'
  }
  return null
}

/** Whether a text is an address (IPv4 or IPv6), which is what can be trusted on its own. */
export function isAddress(text: string): boolean {
  return (
    /^(?:\d{1,3}\.){3}\d{1,3}$/.test(text) || (text.includes(':') && /^[0-9a-f:.]+$/i.test(text))
  )
}
