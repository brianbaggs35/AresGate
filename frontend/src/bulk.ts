import { CircleCheckBig, BellOff, RotateCcw, Search } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { BulkResult, IncidentStatus } from '@/api/incidents'
import type { VerdictKind } from '@/api/verdicts'
import { formatCount } from '@/format'
import { STATUS } from '@/incidents'
import { VERDICT } from '@/verdicts'

/** What can be changed in many incidents at once: what is being done about them, or what is
 * thought of what they are about. */
export type Change = { status: IncidentStatus } | { verdict: VerdictKind }

/** A change to this many incidents, or to all that match a search, is looked over (and counted by
 * the API) before it is made. A smaller one is made at once, and can be taken back. */
export const LOOK_OVER_FROM = 10

interface StatusStep {
  status: IncidentStatus
  /** What the button says: the action. */
  label: string
  icon: NonNullable<IconProps['icon']>
}

/** The statuses to change to, in the order of the work: as buttons, named for what they do. */
export const STATUS_STEPS: readonly StatusStep[] = [
  { status: 'investigating', label: 'Start investigating', icon: Search },
  { status: 'resolved', label: 'Resolve', icon: CircleCheckBig },
  { status: 'dismissed', label: 'Dismiss', icon: BellOff },
  { status: 'open', label: 'Reopen', icon: RotateCcw },
]

export function incidentsOf(count: number): string {
  return count === 1 ? '1 incident' : `${formatCount(count)} incidents`
}

function signalsOf(count: number): string {
  return count === 1 ? '1 signal' : `${formatCount(count)} signals`
}

const isStatus = (change: Change): change is { status: IncidentStatus } => 'status' in change

/** What the change is, as the button that goes ahead says it: "Resolve", "Not suspicious". */
export function labelOf(change: Change): string {
  if (isStatus(change)) {
    return (STATUS_STEPS.find(({ status }) => status === change.status) as StatusStep).label
  }
  return VERDICT[change.verdict].label
}

/** What it asks before it is made: "Resolve 12 incidents?" */
export function askedAs(change: Change, incidents: number): string {
  const what = incidentsOf(incidents)
  if (isStatus(change)) return `${labelOf(change)} ${what}?`
  const verb = incidents === 1 ? 'is' : 'are'
  return `Say ${what} ${verb} ${VERDICT[change.verdict].predicate.replace(/^is /, '')}?`
}

/** What a status is, after the change: "marked as resolved", "reopened". */
function becoming(status: IncidentStatus): string {
  return status === 'open' ? 'reopened' : `marked as ${STATUS[status].label.toLowerCase()}`
}

/** "it already is resolved", "all already are resolved". */
function alreadyIn(incidents: number, status: IncidentStatus): string {
  const which = incidents === 1 ? 'it' : 'all'
  const verb = incidents === 1 ? 'is' : 'are'
  return `${which} already ${verb} ${STATUS[status].label.toLowerCase()}`
}

/** "one verdict", "12 verdicts". */
function verdictsOf(count: number): string {
  return count === 1 ? 'one verdict' : `${formatCount(count)} verdicts`
}

/** The incidents a verdict could not be given for, as the reason they are left out. */
function leftOut(skipped: number): string {
  const one = skipped === 1
  return `${incidentsOf(skipped)} name${one ? 's' : ''} no address and ${one ? 'has' : 'have'} no alert to judge by, so ${one ? 'it is' : 'they are'} left out.`
}

function statusWouldDo(status: IncidentStatus, result: BulkResult, about: string): string[] {
  const { incidents, changed } = result
  if (changed === 0) return [about, `Nothing to change: ${alreadyIn(incidents, status)}.`]
  const already = incidents - changed
  if (already === 0) return [about, `All will be ${becoming(status)}.`]
  const verb = already === 1 ? 'is' : 'are'
  return [
    about,
    `${formatCount(changed)} will be ${becoming(status)}; ${formatCount(already)} already ${verb}.`,
  ]
}

function verdictWouldDo(verdict: VerdictKind, result: BulkResult, about: string): string[] {
  const { verdicts, skipped } = result
  const paragraphs = [about]
  if (verdicts === 0) {
    paragraphs.push('Nothing to change: it is already said of all of them.')
  } else {
    const count = verdictsOf(verdicts)
    paragraphs.push(
      `${count.charAt(0).toUpperCase()}${count.slice(1)} will be remembered as ${VERDICT[verdict].label.toLowerCase()}, one for each address or alert. A verdict holds for everything about it, so incidents you did not pick can change too.`,
    )
  }
  if (skipped > 0) paragraphs.push(leftOut(skipped))
  return paragraphs
}

/** What it says it would do, from what the API worked out, a sentence to a paragraph. */
export function wouldDo(change: Change, result: BulkResult): string[] {
  const about = `${incidentsOf(result.incidents)}, with ${signalsOf(result.signals)}.`
  return isStatus(change)
    ? statusWouldDo(change.status, result, about)
    : verdictWouldDo(change.verdict, result, about)
}

/** Whether there is nothing in it to go ahead with. */
export function nothingToDo(change: Change, result: BulkResult): boolean {
  return isStatus(change) ? result.changed === 0 : result.verdicts === 0
}

function statusDid(status: IncidentStatus, result: BulkResult): string {
  const { incidents, changed } = result
  if (changed === 0) return `Nothing changed: ${alreadyIn(incidents, status)}.`
  const lead =
    status === 'open'
      ? `Reopened ${incidentsOf(changed)}`
      : `Marked ${incidentsOf(changed)} as ${STATUS[status].label.toLowerCase()}`
  const already = incidents - changed
  if (already === 0) return `${lead}.`
  return `${lead}. ${formatCount(already)} already ${already === 1 ? 'was' : 'were'}.`
}

function verdictDid(verdict: VerdictKind, result: BulkResult): string {
  const { verdicts, changed, skipped } = result
  const lead =
    verdicts === 0
      ? `Nothing changed: it is already said of ${incidentsOf(result.incidents - skipped)}.`
      : `Remembered ${verdictsOf(verdicts)} as ${VERDICT[verdict].label.toLowerCase()}, for ${incidentsOf(changed)}.`
  return skipped > 0 ? `${lead} ${incidentsOf(skipped)} left out: nothing to judge by.` : lead
}

/** What it says when it was made: "Marked 3 incidents as resolved." */
export function didDo(change: Change, result: BulkResult): string {
  return isStatus(change) ? statusDid(change.status, result) : verdictDid(change.verdict, result)
}
