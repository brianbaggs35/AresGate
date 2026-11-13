import { apiGet, apiPost, apiPut } from '@/api/client'
import type { DashboardWindow, WindowInfo } from '@/api/dashboard'
import type {
  FamilyBrief,
  Incident,
  IncidentStatus,
  Lane,
  Occurrence,
  OwnerCall,
  Program,
  Stage,
} from '@/api/incidents'
import type { Severity } from '@/severity'

/** Whether an AI has judged a kind of incident, you have called it, or neither yet. */
export const JUDGED = ['ai', 'owner', 'waiting'] as const
export type Judged = (typeof JUDGED)[number]

/** From what programs reported to what needs a person, in the order they are narrowed down. */
export interface Funnel {
  /** Every time a program reported an alert. */
  reports: number
  /** Reports of something another program had already reported. */
  duplicates: number
  /** Reports of something that had just been reported again by the same program. */
  repeats: number
  /** What is left: each alert counted once. */
  alerts: number
  incidents: number
  families: number
  threats: number
  suspects: number
  background: number
  muted: number
  handled: number
}

/** How many of the kinds of incident that are going on have been judged. */
export interface Coverage {
  families: number
  judged: number
  owned: number
  waiting: number
}

/** A kind of incident and what the incidents of it that are going on come to. */
export interface Family extends FamilyBrief {
  alerts: number
  /** How many different addresses (or rules) they are about. */
  actors: number
  worst: Severity
  first_seen_at: string
  last_seen_at: string
  threats: number
  suspects: number
  background: number
  /** When it was first seen to differ from what it was when it was judged. */
  changed_at: string | null
  /** How, in words, a line each: none while it is as it was. */
  changes: string[]
}

/** What is offered about a kind from what you have decided of its incidents. It is never done
 * unless you say yes. */
export interface Suggestion {
  /** background: always set it aside. watch: never set it aside. */
  call: OwnerCall
  /** How many of the incidents of it you decided closed them as benign, and how many you took up. */
  benign: number
  loud: number
  /** How many incidents that are going on it would move: out of view, or back into it. */
  moves: number
  reason: string
}

/** A kind with something to offer about it. */
export interface SuggestedKind {
  id: number
  label: string
  suggestion: Suggestion
}

export interface Overview {
  window: WindowInfo
  funnel: Funnel
  coverage: Coverage
  /** Whether an AI is watching, which is when its agreement is needed for a threat. */
  watching: boolean
  threat_from: number
  families: Family[]
  suggestions: SuggestedKind[]
  /** What the threat hunter's last run flagged among the incidents going on, whatever lane they
   * are in: it only reads, so its word is not one of the lanes. */
  hunted: HuntedPage
}

/** An incident going on that the threat hunter flagged, and what it said of it. */
export interface Hunted {
  id: number
  title: string
  severity: string
  agent_id: number
  agent_name: string
  run_id: number
  finding: string
  action: string
}

export interface HuntedPage {
  /** How many incidents going on it flagged in all, and the first few. */
  total: number
  items: Hunted[]
}

export interface FamilyPage {
  total: number
  items: Family[]
}

export interface FamilyDetail extends Family {
  provider: string | null
  model: string | null
  owner_call_at: string | null
  /** What is behind the call on the kind, a fact to a line. */
  why: string[]
  /** What is offered about it from what you have decided of its incidents, if anything. */
  suggestion: Suggestion | null
  /** The incidents of it going on, the most recent first. */
  sample: Incident[]
}

/** What came of asking the AI about a kind: when it could not be asked, `reason` says why. */
export interface Judgement {
  ok: boolean
  reason: string | null
  family: FamilyDetail
}

export interface FamilyQuery {
  lane?: Lane
  judged?: Judged
  q?: string
  limit?: number
  offset?: number
}

export function fetchOverview(window: DashboardWindow): Promise<Overview> {
  return apiGet<Overview>(`/threats/overview?window=${window}`)
}

export function fetchFamilies(query: FamilyQuery = {}): Promise<FamilyPage> {
  const params = new URLSearchParams()
  if (query.lane) params.set('lane', query.lane)
  if (query.judged) params.set('judged', query.judged)
  if (query.q) params.set('q', query.q)
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const text = params.toString()
  return apiGet<FamilyPage>(text ? `/threats/families?${text}` : '/threats/families')
}

export function fetchFamily(id: number): Promise<FamilyDetail> {
  return apiGet<FamilyDetail>(`/threats/families/${id}`)
}

/** Says what is to be done with a whole kind of incident, or takes your word back (null). */
export function callFamily(
  id: number,
  call: OwnerCall | null,
  csrfToken: string,
): Promise<FamilyDetail> {
  return apiPut<FamilyDetail>(`/threats/families/${id}/call`, { call }, csrfToken)
}

/** Says not now to what is offered about a kind: it is offered again once you have decided twice
 * as many of its incidents. */
export function dismissSuggestion(id: number, csrfToken: string): Promise<FamilyDetail> {
  return apiPost<FamilyDetail>(`/threats/families/${id}/suggestion/dismiss`, {}, csrfToken)
}

/** Asks the AI what a kind of incident is. */
export function judgeFamily(id: number, csrfToken: string): Promise<Judgement> {
  return apiPost<Judgement>(`/threats/families/${id}/judge`, {}, csrfToken)
}

/** Whether a link between two steps of a chain was seen, or only inferred from the device and the
 * time between them. */
export type ChainLink = 'confirmed' | 'inferred'
export type ChainRole = 'attacker' | 'callout'

/** An attack across two devices: an outside address that got in by a flaw, and the device it got
 * into calling out afterwards. */
export interface Chain {
  id: number
  /** The device it went through, and what it is called when that is known. */
  device: string
  device_name: string | null
  first_seen_at: string
  last_seen_at: string
  /** Whether the device was seen doing what a taken-over device does, and not only calling out. */
  confirmed: boolean
  steps: number
  severity: Severity
  /** A threat while any step still needs attention; null once all are handled or muted. */
  lane: Lane | null
  /** Who got in, and where the device then called, in a sentence. */
  summary: string
}

/** One incident of a chain, and the evidence behind it. */
export interface ChainStep {
  role: ChainRole
  link: ChainLink
  reason: string
  incident_id: number
  title: string
  subject: string
  /** What the subject is called, by its reverse lookup, where it has a name. */
  subject_name: string | null
  severity: Severity
  status: IncidentStatus
  first_seen_at: string
  last_seen_at: string
  signal_count: number
  /** How many alerts another program also reported, which count once. */
  duplicates: number
  sources: Program[]
  stages: Stage[]
  /** What the programs said of the signals that name the device. */
  evidence: Occurrence[]
}

export interface ChainPage {
  total: number
  items: Chain[]
}

export interface ChainDetail extends Chain {
  /** The steps in the order they happened. */
  path: ChainStep[]
  /** Why it is a threat, a fact to a line. */
  why: string[]
}

export interface ChainQuery {
  confirmed?: boolean
  limit?: number
  offset?: number
}

export function fetchChains(query: ChainQuery = {}): Promise<ChainPage> {
  const params = new URLSearchParams()
  if (query.confirmed !== undefined) params.set('confirmed', String(query.confirmed))
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  const text = params.toString()
  return apiGet<ChainPage>(text ? `/threats/chains?${text}` : '/threats/chains')
}

export function fetchChain(id: number): Promise<ChainDetail> {
  return apiGet<ChainDetail>(`/threats/chains/${id}`)
}
