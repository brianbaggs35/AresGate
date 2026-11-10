import { CircleHelp, ShieldAlert, ShieldCheck, TriangleAlert, type LucideIcon } from '@lucide/vue'

import type { Judgement, SubjectKind } from '@/api/threatIntel'

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
