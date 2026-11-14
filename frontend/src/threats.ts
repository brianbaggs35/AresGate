import {
  Anchor,
  Binoculars,
  Eye,
  EyeOff,
  Globe,
  House,
  KeyRound,
  ShieldAlert,
  Waves,
  Workflow,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { CallBasis, Call, FamilyBrief, Lane, OwnerCall, Stage } from '@/api/incidents'
import type { Coverage, Funnel, Judged } from '@/api/threats'
import type { Lanes, ThreatDraft, ThreatPreview, ThreatSettings } from '@/api/threatSettings'
import { formatCount } from '@/format'
import { CLASSIFICATION } from '@/triage'

type Icon = NonNullable<IconProps['icon']>

interface LaneLook {
  label: string
  plural: string
  /** A theme color. */
  color: string
  icon: Icon
  /** What being in it means, in a sentence. */
  meaning: string
}

/** What each lane looks like. Like a severity, never just a color: each has its icon and name. */
export const LANE: Readonly<Record<Lane, LaneLook>> = {
  threat: {
    label: 'Threat',
    plural: 'Threats',
    color: 'error',
    icon: ShieldAlert,
    meaning: 'Highly likely to be a real attack. Look at these first.',
  },
  suspect: {
    label: 'Suspect',
    plural: 'Suspects',
    color: 'warning',
    icon: Eye,
    meaning: 'Could be real, but AresGate is not sure enough to call it a threat. Worth a look.',
  },
  background: {
    label: 'Background',
    plural: 'Background',
    color: 'secondary',
    icon: Waves,
    meaning:
      'Scanning and probing that is part of life on the internet, or what AresGate cannot tell yet. Kept and searchable, and out of your way.',
  },
}

interface StageLook {
  label: string
  icon: Icon
  meaning: string
}

/** How far an attack got, in the order it gets there. */
export const STAGE: Readonly<Record<Stage, StageLook>> = {
  recon: {
    label: 'Looking around',
    icon: Binoculars,
    meaning: 'Scanning and probing to find what is there.',
  },
  access: {
    label: 'Trying to get in',
    icon: KeyRound,
    meaning: 'Guessing passwords or trying a flaw in a service.',
  },
  foothold: {
    label: 'Sign it worked',
    icon: Anchor,
    meaning: 'Something says it got in, or that a device is talking to an attacker.',
  },
}

export const STAGES_IN_ORDER: readonly Stage[] = ['recon', 'access', 'foothold']

/** Whose word a call on an incident is, as it follows "Judged by": the name of the voice. */
export const BASIS: Readonly<Record<CallBasis, { who: string; sentence: string }>> = {
  owner: { who: 'You', sentence: 'You said so, about this kind of incident.' },
  reading: { who: 'The AI', sentence: 'The AI read this incident.' },
  family: { who: 'The AI', sentence: 'The AI judged this kind of incident as a whole.' },
}

interface OwnerLook {
  label: string
  /** What the button that says it is called. */
  button: string
  icon: Icon
  meaning: string
}

/** What you can say of a whole kind of incident. */
export const OWNER_CALL: Readonly<Record<OwnerCall, OwnerLook>> = {
  background: {
    label: 'You set it aside',
    button: 'Always background',
    icon: EyeOff,
    meaning: 'Every incident of this kind is background, whatever the AI says.',
  },
  watch: {
    label: 'You watch it',
    button: 'Never set aside',
    icon: Eye,
    meaning: 'No incident of this kind is set aside by the AI. They stay where the rules put them.',
  },
}

/** The kinds the list can be narrowed to by who has judged them. */
export const JUDGED_FILTERS: readonly { value: Judged | null; label: string }[] = [
  { value: null, label: 'Any' },
  { value: 'ai', label: 'Judged by the AI' },
  { value: 'owner', label: 'Called by you' },
  { value: 'waiting', label: 'Not judged yet' },
]

const REACH: Readonly<Record<FamilyBrief['reach'], { label: string; icon: Icon }>> = {
  internet: { label: 'From the internet', icon: Globe },
  network: { label: 'Inside your network', icon: House },
  rule: { label: 'A rule with no address', icon: Workflow },
}

export function reachOf(reach: FamilyBrief['reach']) {
  return REACH[reach]
}

/** What is thought of a kind of incident: your word first, then the AI's, else that no one has
 * judged it yet. */
export function verdictOf(
  family: Pick<FamilyBrief, 'owner_call' | 'classification' | 'confidence'>,
) {
  if (family.owner_call) return { who: 'owner' as const, text: OWNER_CALL[family.owner_call].label }
  if (family.classification) {
    const sure = family.confidence === null ? '' : `, ${family.confidence.toString()}% sure`
    return { who: 'ai' as const, text: `AI: ${CLASSIFICATION[family.classification].label}${sure}` }
  }
  return { who: 'none' as const, text: 'Not judged yet' }
}

/** The sentence that says whose word an incident's call is. */
export function callSentence(call: Call): string {
  return `${CLASSIFICATION[call.classification].label}, ${call.confidence.toString()}% sure. ${BASIS[call.basis].sentence}`
}

export interface FunnelStep {
  key: 'reports' | 'alerts' | 'incidents' | Lane
  label: string
  count: number
  /** What was taken out on the way to it, or what it is. */
  detail: string
  /** How wide its bar is, from 0 to 100 (not to scale: a log scale shows the small ones). */
  width: number
}

function widthOf(count: number, most: number): number {
  if (count <= 0 || most <= 0) return 0
  // Seventy thousand and four on one linear bar leaves the four invisible, so the bars go by the
  // number of digits and are then never thinner than a sliver.
  return Math.max(4, Math.round((Math.log10(count + 1) / Math.log10(most + 1)) * 100))
}

/** From what programs reported to the lanes, as the steps of a funnel. The lanes only count
 * incidents that are going on, which are not in the window's counts. */
export function funnelSteps(funnel: Funnel): FunnelStep[] {
  const most = Math.max(funnel.reports, 1)
  const steps: Omit<FunnelStep, 'width'>[] = [
    {
      key: 'reports',
      label: 'Reports',
      count: funnel.reports,
      detail: 'Every time a program reported an alert.',
    },
    {
      key: 'alerts',
      label: 'Alerts',
      count: funnel.alerts,
      detail: `${formatCount(funnel.duplicates)} were another program saying the same thing, and ${formatCount(funnel.repeats)} the same alert again.`,
    },
    {
      key: 'incidents',
      label: 'Incidents',
      count: funnel.incidents,
      detail: `Alerts about the same thing, grouped. ${formatCount(funnel.families)} kinds.`,
    },
    { key: 'threat', label: 'Threats', count: funnel.threats, detail: LANE.threat.meaning },
    { key: 'suspect', label: 'Suspects', count: funnel.suspects, detail: LANE.suspect.meaning },
    {
      key: 'background',
      label: 'Background',
      count: funnel.background,
      detail: `Out of your way, never thrown away. ${formatCount(funnel.muted)} you muted and ${formatCount(funnel.handled)} handled are not counted.`,
    },
  ]
  return steps.map((step) => ({ ...step, width: widthOf(step.count, most) }))
}

/** A count and what it counts, such as "1 alert" or "3,000 alerts". */
function counted(count: number, one: string): string {
  const noun = count === 1 ? one : one + 's'
  return `${formatCount(count)} ${noun}`
}

/** The funnel in a sentence, for the top of the page. */
export function funnelSentence(funnel: Funnel, window: string): string {
  if (funnel.reports === 0) return `No program reported anything in ${window}.`
  const lead =
    funnel.reports === funnel.alerts
      ? `${counted(funnel.alerts, 'alert')} in ${window}`
      : `${counted(funnel.reports, 'report')} in ${window} came to ${counted(funnel.alerts, 'alert')}`
  const incidents = counted(funnel.incidents, 'incident')
  if (funnel.threats === 0 && funnel.suspects === 0) {
    return `${lead}, grouped into ${incidents}. None of them is a threat or worth a look.`
  }
  const threats = counted(funnel.threats, 'threat')
  const suspects = counted(funnel.suspects, 'suspect')
  return `${lead}, grouped into ${incidents}: ${threats} and ${suspects}.`
}

/** How much of the work of telling kinds apart has been done. */
export function coverageSentence(coverage: Coverage, watching: boolean): string {
  if (coverage.families === 0) return 'There are no kinds of incident to judge.'
  const done = coverage.judged + coverage.owned
  const base = `${formatCount(done)} of ${formatCount(coverage.families)} kinds have been judged.`
  if (coverage.waiting === 0) return base
  return watching
    ? `${base} ${formatCount(coverage.waiting)} are waiting for the AI.`
    : `${base} ${formatCount(coverage.waiting)} are waiting: turn on the AI and let it read by itself, and it judges them.`
}

/** The lane to open the Threats page on: the first with something in it. */
export function firstLane(funnel: Funnel | null): Lane {
  if (!funnel || funnel.threats > 0) return 'threat'
  if (funnel.suspects > 0) return 'suspect'
  return 'background'
}

// ---- the settings page ----

export const THREAT_MIN = 5
export const THREAT_MAX = 100
export const THREAT_STEP = 5

export const EXPOSURE_CHOICES = [
  {
    value: 'none',
    title: 'Nothing is open to the internet',
    detail: 'Everything from outside is expected to be turned away, so a scan is only background.',
  },
  {
    value: 'some',
    title: 'Some services are open',
    detail: 'Attacks on the ports below matter more than the same attacks on a closed port.',
  },
  {
    value: 'unknown',
    title: "I'm not sure",
    detail: 'AresGate treats the network as it does when it knows nothing about it.',
  },
] as const

/** The draft that saving would keep, to begin with what is kept. */
export function draftOf(kept: ThreatSettings): ThreatDraft {
  return {
    threat_from: kept.threat_from,
    ai_may_clear: kept.ai_may_clear,
    clear_from: kept.clear_from,
    ai_confirms: kept.ai_confirms,
    exposure: kept.exposure,
    exposed_ports: [...kept.exposed_ports],
    notes: kept.notes,
    important_drop: kept.important_drop,
    low_raise: kept.low_raise,
    ai_gives_verdicts: kept.ai_gives_verdicts,
  }
}

/** Whether two drafts say the same. */
export function sameDraft(one: ThreatDraft, other: ThreatDraft): boolean {
  return (
    one.threat_from === other.threat_from &&
    one.ai_may_clear === other.ai_may_clear &&
    one.clear_from === other.clear_from &&
    one.ai_confirms === other.ai_confirms &&
    one.exposure === other.exposure &&
    one.notes === other.notes &&
    one.important_drop === other.important_drop &&
    one.low_raise === other.low_raise &&
    one.ai_gives_verdicts === other.ai_gives_verdicts &&
    one.exposed_ports.length === other.exposed_ports.length &&
    one.exposed_ports.every((port, index) => port === other.exposed_ports[index])
  )
}

/** The ports in a field as numbers, once each and in order, and the words that are not a port. */
export function portsOf(text: string): { ports: number[]; bad: string[] } {
  const words = text.split(/[\s,;]+/).filter(Boolean)
  const bad = words.filter(
    (word) => !/^\d{1,5}$/.test(word) || Number(word) < 1 || Number(word) > 65535,
  )
  const ports = [...new Set(words.filter((word) => !bad.includes(word)).map(Number))].sort(
    (a, b) => a - b,
  )
  return { ports, bad }
}

/** How the threat bar compares with the usual one. */
function barNote(from: number, fallback: number): string {
  if (from < fallback) {
    return 'Lower than usual: more will be called threats, and more of them will be nothing.'
  }
  if (from > fallback) {
    return 'Higher than usual: only the surest will be called threats, and one that is real may be a suspect.'
  }
  return 'The usual: an incident is a threat when AresGate is this sure it is a real attack.'
}

/** What the threat bar means, in a sentence. */
export function threatSentence(from: number, fallback: number): string {
  return `Incidents AresGate is at least ${from.toString()} out of 100 sure of are threats. ${barNote(from, fallback)}`
}

/** What the AI's bar for setting an incident aside means. */
export function clearSentence(from: number, minimum: number): string {
  const how =
    from <= minimum ? 'As low as it can go.' : 'The surer it has to be, the less it sets aside.'
  return `The AI sets an incident aside when it is at least ${from.toString()}% sure it is harmless or a probe. ${how}`
}

/** What moving the bar for the devices that matter means, in a sentence. A chain of attacks and
 * what the AI is sure of are shown whatever the bar is. */
export function importanceSentence(way: 'drop' | 'raise', points: number): string {
  if (points === 0) {
    return way === 'drop'
      ? 'An incident that touched an important device is shown at the same bar as any other.'
      : 'An incident that touched only a guest or an IoT device is shown at the same bar as any other.'
  }
  const count = `${points.toString()} ${points === 1 ? 'point' : 'points'}`
  return way === 'drop'
    ? `An incident that touched an important device is shown when AresGate is ${count} less sure than usual.`
    : `An incident that touched only a guest or an IoT device needs ${count} more before it is shown. Anything that is a chain of attacks is shown regardless.`
}

/** The lanes as the rows of a table, now and with the settings as asked. */
export function laneRows(
  preview: ThreatPreview,
): { key: keyof Lanes; label: string; now: number; after: number }[] {
  const rows: [keyof Lanes, string][] = [
    ['threats', 'Threats'],
    ['suspects', 'Suspects'],
    ['background', 'Background'],
    ['cleared', 'Set aside by the AI'],
    ['muted', 'Called quiet by you'],
  ]
  return rows.map(([key, label]) => ({
    key,
    label,
    now: preview.now[key],
    after: preview.after[key],
  }))
}

/** What saving would do to the lanes, in a sentence. */
export function laneSentence(preview: ThreatPreview): string {
  const { now, after } = preview
  const changes: [number, string, string][] = [
    [after.threats - now.threats, 'threat', 'threats'],
    [after.suspects - now.suspects, 'suspect', 'suspects'],
    [after.background - now.background, 'in the background', 'in the background'],
  ]
  const parts = changes
    .filter(([change]) => change !== 0)
    .map(([change, one, many]) => {
      const count = Math.abs(change)
      const word = count === 1 ? one : many
      return `${change > 0 ? '+' : '−'}${formatCount(count)} ${word}`
    })
  if (parts.length === 0) return 'Nothing that is going on now would move to another lane.'
  return `Saving would change the lanes by ${parts.join(', ')}.`
}
