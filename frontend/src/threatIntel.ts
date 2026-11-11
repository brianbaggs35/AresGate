import { CircleHelp, ShieldAlert, ShieldCheck, TriangleAlert, type LucideIcon } from '@lucide/vue'

import type { Judgement, Lookup, Ruling, SubjectKind, Verdict } from '@/api/threatIntel'

/** What each kind of subject is called. */
export const KIND: Record<SubjectKind, string> = {
  ip: 'IP address',
  domain: 'Domain',
  url: 'Web address',
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
