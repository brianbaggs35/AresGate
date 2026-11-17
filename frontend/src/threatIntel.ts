import {
  Bug,
  CircleHelp,
  EyeOff,
  Fingerprint,
  Globe,
  Link2,
  MonitorSmartphone,
  Network,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  type LucideIcon,
} from '@lucide/vue'

import { formatCount } from '@/format'
import type { AssetStanding } from '@/api/assets'
import type { Judgement, Lookup, Provider, Ruling, SubjectKind, Verdict } from '@/api/threatIntel'
import type { DeviceState } from '@/api/threatCatalog'

/** What each kind of subject is called. */
export const KIND: Record<SubjectKind, string> = {
  ip: 'IP address',
  domain: 'Domain',
  url: 'Web address',
}

/** The kinds of threat intelligence, as the tabs of the page: what the intelligence is about, not
 * which service it comes from. A service gives intelligence of every kind it answers about. */
export type TypeKey = SubjectKind | 'cve' | 'device'

export interface TypeLook {
  key: TypeKey
  /** The tab. */
  name: string
  icon: LucideIcon
  /** What the search box is labelled, and what an example in it looks like, for the kinds that
   * are searched for by hand. */
  label: string
  placeholder: string
  /** What it answers about, as the end of "Look up ...". */
  about: string
  /** What there are many of, in a sentence. */
  plural: string
}

/** The tabs, in order: what a service is asked about by hand first, then what AresGate reads from
 * NVD and Fingerbank in the background. */
export const TYPES: readonly TypeLook[] = [
  {
    key: 'ip',
    name: 'IP addresses',
    icon: Network,
    label: 'IP address',
    placeholder: '203.0.113.7',
    about: 'an IP address',
    plural: 'IP addresses',
  },
  {
    key: 'domain',
    name: 'Domains',
    icon: Globe,
    label: 'Domain',
    placeholder: 'example.com',
    about: 'a domain',
    plural: 'domains',
  },
  {
    key: 'url',
    name: 'Web addresses',
    icon: Link2,
    label: 'Web address',
    placeholder: 'https://example.com/login',
    about: 'a web address',
    plural: 'web addresses',
  },
  {
    key: 'cve',
    name: 'CVEs',
    icon: Bug,
    label: '',
    placeholder: '',
    about: 'a vulnerability',
    plural: 'vulnerabilities',
  },
  {
    key: 'device',
    name: 'Devices',
    icon: MonitorSmartphone,
    label: '',
    placeholder: '',
    about: 'a device',
    plural: 'devices',
  },
]

/** One kind of threat intelligence, by its key. */
export function typeOf(key: TypeKey): TypeLook {
  return TYPES.find((one) => one.key === key) as TypeLook
}

export interface JudgementLook {
  /** The judgement as a sentence, for a report. */
  label: string
  /** The judgement in a word or two, for a list and a filter. */
  short: string
  color: string | undefined
  icon: LucideIcon
}

/** How each judgement is shown, wherever one is. */
export const JUDGEMENT: Record<Judgement, JudgementLook> = {
  malicious: {
    label: 'Reported as malicious',
    short: 'Malicious',
    color: 'error',
    icon: ShieldAlert,
  },
  suspicious: {
    label: 'Reported as suspicious',
    short: 'Suspicious',
    color: 'warning',
    icon: TriangleAlert,
  },
  clean: { label: 'No engine flagged it', short: 'Clean', color: 'success', icon: ShieldCheck },
  unknown: { label: 'No report yet', short: 'No report', color: undefined, icon: CircleHelp },
}

/** The judgements in the order they matter: what was flagged first. */
export const JUDGEMENTS: readonly Judgement[] = ['malicious', 'suspicious', 'clean', 'unknown']

export interface RulingLook {
  /** What the owner said, as a sentence about the subject. */
  label: string
  /** What the owner said, in a word. */
  short: string
  /** What saying it asks of AresGate, for the choice. */
  effect: string
  color: string
  icon: LucideIcon
}

/** How what the owner rules is shown, wherever one is. */
export const RULING: Record<Verdict, RulingLook> = {
  safe: {
    label: 'You ruled it safe',
    short: 'Safe',
    effect: 'I know it. Treat it as harmless, whatever a service says.',
    color: 'success',
    icon: ShieldCheck,
  },
  suspicious: {
    label: 'You ruled it suspicious',
    short: 'Suspicious',
    effect: 'Treat it with suspicion, even if no service has flagged it.',
    color: 'warning',
    icon: TriangleAlert,
  },
}

/** An answer with the owner's ruling put on it, or taken off: what it comes to follows the ruling,
 * and what VirusTotal made of it stays what it was. */
export function withRuling(lookup: Lookup, ruling: Ruling | null): Lookup {
  return {
    ...lookup,
    ruling,
    judgement: ruling ? ruling.judgement : lookup.reported_judgement,
  }
}

export interface ProviderLook {
  key: Provider
  /** What the service is called. */
  name: string
  /** The kinds of subject it answers about. */
  kinds: readonly SubjectKind[]
  /** What its "clean" says, where it is not what the other services say. */
  clean: string
  /** What its score is called, or null where it gives none. */
  score: string | null
  /** Whether it has a time of its own for when it analysed a subject. */
  analysis: boolean
  /** What searching for something tells the service. */
  sharing: string | null
}

/** The services, in the order their results come. */
export const PROVIDERS: readonly ProviderLook[] = [
  {
    key: 'virustotal',
    name: 'VirusTotal',
    kinds: ['ip', 'domain', 'url'],
    clean: 'No engine flagged it',
    score: 'Community score',
    analysis: true,
    sharing:
      "What you search for is added to VirusTotal's shared data, so keep private names out of searches.",
  },
  {
    key: 'otx',
    name: 'AlienVault OTX',
    kinds: ['ip', 'domain'],
    clean: 'Listed as safe',
    score: 'Reputation score',
    analysis: false,
    sharing: null,
  },
  {
    key: 'greynoise',
    name: 'GreyNoise',
    kinds: ['ip'],
    clean: 'Benign or a common business service',
    score: null,
    analysis: false,
    sharing: null,
  },
]

/** One service, by its key. */
export function providerOf(key: Provider): ProviderLook {
  return PROVIDERS.find((one) => one.key === key) as ProviderLook
}

/** The services that answer about a kind of subject. */
export function providersFor(kind: SubjectKind): ProviderLook[] {
  return PROVIDERS.filter((one) => one.kinds.includes(kind))
}

/** The judgement of an answer as a sentence, in the words of the service that gave it. */
export function judgementLabel(provider: Provider, judgement: Judgement): string {
  return judgement === 'clean' ? providerOf(provider).clean : JUDGEMENT[judgement].label
}

/** What an answer's counts say, in a sentence: what the service made of it, whatever the owner
 * ruled. */
export function summaryOf(lookup: Lookup): string {
  const { malicious, suspicious } = lookup
  const name = lookup.provider_name
  if (lookup.provider === 'virustotal') {
    const engines = malicious + suspicious + lookup.harmless + lookup.undetected
    switch (lookup.reported_judgement) {
      case 'malicious':
        return `${malicious} of ${engines} engines flagged it as malicious.`
      case 'suspicious':
        return `${suspicious} of ${engines} engines flagged it as suspicious.`
      case 'clean':
        return `None of the ${engines} engines flagged it.`
      case 'unknown':
        return 'VirusTotal has no report on it yet.'
    }
  }
  if (lookup.provider === 'otx') {
    const pulses = malicious + suspicious
    switch (lookup.reported_judgement) {
      case 'clean':
        return 'AlienVault OTX lists it as safe.'
      case 'unknown':
        return 'No pulse on AlienVault OTX names it.'
      default:
        return `${pulses} ${pulses === 1 ? 'pulse names' : 'pulses name'} it, ${
          malicious ? `${malicious} of them also naming` : 'none of them naming'
        } malware, an adversary or an attack technique.`
    }
  }
  switch (lookup.reported_judgement) {
    case 'malicious':
      return 'GreyNoise classifies it as malicious.'
    case 'suspicious':
      return "GreyNoise has seen it scanning the internet, and doesn't classify it."
    case 'clean':
      return 'GreyNoise classifies it as benign, or lists it as a common business service.'
    case 'unknown':
      return `${name} has no report on it.`
  }
}

/** What an answer comes to in a few words, for a row of a list. */
export function tallyOf(lookup: Lookup): string {
  if (lookup.reported_judgement === 'unknown') return 'No report'
  const flagged = lookup.malicious + lookup.suspicious
  if (lookup.provider === 'virustotal') {
    const engines = flagged + lookup.harmless + lookup.undetected
    return `${formatCount(flagged)} of ${formatCount(engines)} flagged`
  }
  if (lookup.provider === 'otx') {
    if (lookup.reported_judgement === 'clean') return 'Listed as safe'
    return `${formatCount(flagged)} ${flagged === 1 ? 'pulse' : 'pulses'}`
  }
  return JUDGEMENT[lookup.reported_judgement].short
}

/** What a kept answer about an address comes to, in a few words, as the service that gave it
 * counts: engines flagging it for VirusTotal, pulses naming it for OTX, how GreyNoise classifies
 * it. Nothing where no service had a report, or there is no standing. */
export function standingTally(
  standing:
    | Pick<AssetStanding, 'provider' | 'reported' | 'malicious' | 'suspicious' | 'engines'>
    | null
    | undefined,
): string {
  if (!standing || standing.reported === 'unknown') return ''
  const flagged = standing.malicious + standing.suspicious
  if (standing.provider === 'otx') {
    return standing.reported === 'clean'
      ? 'AlienVault OTX lists it as safe'
      : `${formatCount(flagged)} ${flagged === 1 ? 'pulse names' : 'pulses name'} it on AlienVault OTX`
  }
  if (standing.provider === 'greynoise') {
    return `GreyNoise: ${JUDGEMENT[standing.reported].short.toLowerCase()}`
  }
  return `${formatCount(flagged)} of ${formatCount(standing.engines)} engines flagged it`
}

export interface DeviceStateLook {
  label: string
  /** What it means, as a sentence about the device. */
  about: string
  color: string | undefined
  icon: LucideIcon
}

/** What Fingerbank made of a device, wherever one is shown. */
export const DEVICE_STATE: Record<DeviceState, DeviceStateLook> = {
  identified: {
    label: 'Identified',
    about: 'Fingerbank recognised it.',
    color: 'success',
    icon: Fingerprint,
  },
  unknown: {
    label: 'Not recognised',
    about: 'Fingerbank has no match for it.',
    color: undefined,
    icon: CircleHelp,
  },
  private: {
    label: 'Private address',
    about:
      'Its hardware address is one the device made up, which hides what it is, so Fingerbank was not asked.',
    color: 'info',
    icon: EyeOff,
  },
}
