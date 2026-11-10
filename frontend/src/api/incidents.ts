import { apiGet, apiPatch, apiPost } from '@/api/client'
import type { VerdictKind } from '@/api/verdicts'
import type { Severity } from '@/severity'

/** What is being done about an incident. */
export const INCIDENT_STATUSES = ['open', 'investigating', 'resolved', 'dismissed'] as const
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number]

/** How sure AresGate is, in a word. */
export type ConfidenceLevel = 'low' | 'medium' | 'high'

/** An integration that reported part of an incident, by its key and by its name. */
export interface Program {
  key: string
  name: string
}

/** What kind of activity its signals say it was: a scan of ports, or guessing at logins. */
export type Activity = 'scan' | 'brute_force'

/** What kind of thing an AI makes of an incident. */
export const CLASSIFICATIONS = ['compromise', 'attack', 'probe', 'noise', 'unclear'] as const
export type Classification = (typeof CLASSIFICATIONS)[number]

/** Where an incident goes on the Threats page: a threat is highly likely to be real, a suspect is
 * worth a look, and background is what AresGate is not sure of or an AI judged to be noise or a
 * probe. */
export const LANES = ['threat', 'suspect', 'background'] as const
export type Lane = (typeof LANES)[number]

/** How far along the path of an attack an incident got: looking, trying to get in, a sign that
 * it worked. */
export const STAGES = ['recon', 'access', 'foothold'] as const
export type Stage = (typeof STAGES)[number]

/** Whose word a call on an incident is: yours on its kind, the AI's reading of this incident, or
 * the AI's judgement of its kind. */
export type CallBasis = 'owner' | 'reading' | 'family'

/** What the AI made of an incident, in a word and how sure it was: for a list. */
export interface Glance {
  classification: Classification
  /** How sure the AI is of it, 0 to 100. */
  confidence: number
}

/** What an AI provider made of an incident: its opinion, kept as it was given. It never changes
 * the incident, and the verdict it suggests is only given if the owner gives it. */
export interface Reading extends Glance {
  headline: string
  story: string
  /** Things to check for yourself, most useful first. */
  checks: string[]
  verdict: VerdictKind | null
  verdict_reason: string | null
  read_at: string
  /** Who read it: the provider's name, and the model. */
  provider: string
  model: string
  /** How many signals it had when it was read. */
  signals_read: number
}

/** What was done about an incident, in a word: an address CrowdSec banned (`banned`, or `partly`
 * when only some of the addresses of a block were), a ban that has run out, an address the
 * firewall or Suricata turned away, nothing yet, or an incident about a rule, with no address to
 * act on. */
export type ResponseState = 'banned' | 'partly' | 'ban_ended' | 'blocked' | 'none' | 'no_address'

/** A decision CrowdSec made about one of an incident's addresses. */
export interface Ban {
  address: string
  /** What kind of remedy it was: a ban, nearly always. */
  kind: string
  scenario: string | null
  /** Where the decision came from, in words. */
  origin: string | null
  /** When AresGate first read it, which is when it knows of it. */
  seen_at: string
  /** When it runs out, if the time CrowdSec said was left is understood. */
  ends_at: string | null
  /** A ban that CrowdSec only pretended to make (its simulation mode). */
  simulated: boolean
  /** Whether it still holds, as far as is known. */
  in_force: boolean
}

/** What was done about an incident: the bans, and how often it was turned away. */
export interface IncidentResponse {
  state: ResponseState
  /** The state in words, for a chip. */
  label: string
  bans: Ban[]
  /** How often the firewall turned the address away, and how often of those after the first
   * ban (null without one), and when it last did. */
  blocked: number
  blocked_since_ban: number | null
  last_blocked_at: string | null
  /** How many alerts Suricata stopped. */
  dropped: number
  /** What AresGate can't tell, and why. */
  unknown: string[]
}

export interface Incident {
  id: number
  title: string
  /** The address the signals are about, or `rule:<integration>:<rule>` where they name none. */
  subject: string
  severity: Severity
  /** How sure AresGate is that it is a real attack, 0 to 100, and in a word. */
  confidence: number
  confidence_level: ConfidenceLevel
  status: IncidentStatus
  first_seen_at: string
  last_seen_at: string
  /** How many signals it has, which can be more than its timeline lists. */
  signal_count: number
  sources: Program[]
  /** Every address in the signals, the subject first. */
  addresses: string[]
  /** Whether an integration banned the address. */
  banned: boolean
  /** What was done about it. */
  response: IncidentResponse
  status_changed_at: string | null
  /** What the owner's verdicts say of it as a whole: a real threat, not suspicious or low
   * priority (because every signal is), or nothing. */
  verdict: VerdictKind | null
  /** How many of its signals each verdict was given of. The ones called not suspicious or low
   * priority are listed and counted in `signal_count`, but leave everything else about the
   * incident to the signals that are not. */
  verdict_counts: Partial<Record<VerdictKind, number>>
  /** How many of its signals your noise filters set aside (Settings, Noise filters). Like the
   * ones a verdict leaves out they are listed and counted in `signal_count`, and count for
   * nothing else. */
  filtered_count: number
  /** What its signals say it was, where they say. */
  activities: Activity[]
  /** How many bursts they came in, with a quarter of an hour of quiet between them: a bot that
   * sweeps the network three times in an afternoon is one incident with three waves. */
  waves: number
  /** How many different destination ports they touched, as far as are kept (`ports_capped`). */
  port_count: number
  ports_capped: boolean
  /** How many other addresses of the subject's block (a /24 or /64) are grouped into it. */
  neighbours: number
  /** What the AI made of it, if it has read it (`IncidentDetail.reading` has the rest). */
  ai: Glance | null
  /** Where it goes: a threat, a suspect or background. Null for one that is over, or that you
   * called not suspicious or low priority. */
  lane: Lane | null
  /** How many of its signals another program had already reported (they count once). */
  duplicates: number
  /** The stages of an attack its signals show, in the order of the path. */
  stages: Stage[]
  /** The kind of incident it is, and what is thought of it by you or an AI. */
  family_id: number | null
  call: Call | null
}

/** What is made of an incident beyond the rules, and whose word it is. */
export interface Call extends Glance {
  basis: CallBasis
}

/** One thing that makes AresGate as sure as it is: the points add up to the confidence. */
export interface Reason {
  rule: string
  points: number
  text: string
}

/** Why a noise filter set a signal aside: it was between two addresses on your network, under the
 * severity that its program has to reach to count, or one of too few low alerts to ask about. */
export type FilteredBy = 'inside' | 'severity' | 'thin'

export interface Signal {
  occurred_at: string
  source: string
  source_name: string
  kind: string
  severity: Severity
  summary: string
  signature: string | null
  src_address: string | null
  src_port: number | null
  dst_address: string | null
  dst_port: number | null
  protocol: string | null
  /** What the owner's verdicts said of it, and the verdict that said it while that exists. */
  verdict: VerdictKind | null
  verdict_rule_id: number | null
  /** Which of your noise filters set it aside, if one did and no verdict was about it. */
  filtered_by: FilteredBy | null
  /** Whether another program had already reported the same thing a moment before. */
  duplicate: boolean
}

/** One thing a program said of an alert, as a label and its value: the rule's number, what was
 * done about it. */
export interface Fact {
  label: string
  value: string
}

/** A technique of the MITRE ATT&CK framework that a program matched an alert to. */
export interface Technique {
  id: string
  tactic: string
  technique: string
}

/** Something an alert names that can be looked up. `kind` is what sort of thing it is: a
 * `hostname`, a `url`, a `user_agent`, a `dns` name, an `sni`, a `user`, a `file` or a `country`. */
export interface Named {
  kind: string
  value: string
}

/** How much the flow an alert is about carried, as its program counted it, in what it gave. */
export interface FlowVolume {
  packets_out: number | null
  packets_in: number | null
  bytes_out: number | null
  bytes_in: number | null
}

/** What one program said of an alert besides who, where and when. A member is empty where the
 * program said nothing for it. */
export interface Evidence {
  facts: Fact[]
  /** Words that sort the alert: the groups of a Wazuh rule, an alert's category. */
  tags: string[]
  mitre: Technique[]
  named: Named[]
  traffic: FlowVolume | null
  /** The machine it is about, and the application it was. */
  host: string | null
  app: string | null
  /** The log line it came from. */
  excerpt: string | null
}

/** A program that reported the same alert as the first did, moments later: it agrees, and it may
 * have seen more. It is not another alert. */
export interface Confirmation {
  source: string
  source_name: string
  signature: string | null
  severity: Severity
  /** How many times it reported it, and when it first and last did. */
  count: number
  first_at: string
  last_at: string
  evidence: Evidence | null
}

/** Signals that say the same thing the same way: one that happened `count` times. */
export interface Occurrence {
  /** The first of them. */
  signal: Signal
  count: number
  last_at: string
  /** How many reports of it another program also made, counted once. */
  duplicates: number
  /** What the program that reported it said besides the basics, where it said any. An incident
   * with a great many occurrences says it only for the busiest. */
  evidence: Evidence | null
  /** The programs that agreed. */
  confirmations: Confirmation[]
}

/** A word, and how many alerts it was said of. */
export interface Counted {
  value: string
  count: number
}

export interface CountedTechnique extends Technique {
  count: number
}

export interface CountedNamed extends Named {
  count: number
}

/** What one program told of an incident: how many alerts it reported, and what kinds of detail it
 * gave besides the basics (an empty list is a program that said no more than that). */
export interface Contribution {
  source: string
  source_name: string
  reports: number
  adds: string[]
}

/** What the programs between them knew of an incident, added up an alert at a time. */
export interface Insights {
  techniques: CountedTechnique[]
  tags: Counted[]
  hosts: Counted[]
  apps: Counted[]
  named: CountedNamed[]
  programs: Contribution[]
}

/** Your word on a whole kind of incident: set all of it aside, or never set any of it aside. */
export type OwnerCall = 'background' | 'watch'

/** A kind of incident: the ones that a program reported in the same words about the same sort of
 * place, and what is thought of all of them. */
export interface FamilyBrief {
  id: number
  /** What its incidents say, without the addresses and numbers that differ. */
  label: string
  source: string
  source_name: string
  /** Where its incidents are from: the internet, your own network, or a rule with no address. */
  reach: 'internet' | 'network' | 'rule'
  /** Your word on it: set all of it aside (`background`), or never set it aside (`watch`). */
  owner_call: OwnerCall | null
  /** What an AI made of the kind as a whole. */
  classification: Classification | null
  confidence: number | null
  reason: string | null
  judged_at: string | null
  /** How many incidents of it are going on. */
  incidents: number
}

/** A device on the network that one of the incident's addresses belongs to. */
export interface IncidentDevice {
  id: number
  address: string
  mac: string
  hostname: string | null
  vendor: string | null
}

export interface IncidentDetail extends Incident {
  reasons: Reason[]
  /** Why its signals are one incident, in plain words, a fact to a line. */
  grouping: string[]
  /** The destination ports they touched, lowest first. */
  ports: number[]
  /** Oldest first. Only the first so many are kept: `signal_count` has them all. */
  signals: Signal[]
  devices: IncidentDevice[]
  /** How many times the firewall turned the subject away around then, or null for an incident
   * about a rule rather than an address. */
  blocked: number | null
  reading: Reading | null
  /** Why it is in the lane it is in, a fact to a line. */
  why: string[]
  /** Its signals grouped by what they say, in the order each first happened. */
  occurrences: Occurrence[]
  family: FamilyBrief | null
  /** What the programs said besides the basics, added up. Null when none said anything. */
  insights: Insights | null
}

/** One term of a search as AresGate understood it: what it is about and how to read it back. */
export interface SearchTerm {
  /** `source`, `severity` and the like, or null for plain words. */
  field: string | null
  /** In words to show: `Source: Wazuh`, `Not address: 10.0.0.0/8`. */
  label: string
  negated: boolean
  /** Where it was in the text of the search: the characters from `start` up to `end`. */
  start: number
  end: number
}

/** An integration and how many of the incidents found it reported part of. */
export interface SourceCount {
  key: string
  name: string
  count: number
}

/** How the incidents found are spread, whatever page of them is on screen. */
export interface Facets {
  severity: Record<Severity, number>
  /** The most first. */
  sources: SourceCount[]
}

export interface IncidentPage {
  total: number
  items: Incident[]
  /** The search in words, as it was understood: one for each term. */
  terms: SearchTerm[]
  facets: Facets
  /** How many incidents there are in each status, whatever the search was for except which
   * verdicts it asked about. */
  counts: Record<IncidentStatus, number>
  /** How many more it would have found if it had not left out the ones the owner called not
   * suspicious or low priority. */
  quieted: number
}

/** What to look for. Nothing given matches everything. */
export interface IncidentQuery {
  statuses?: readonly IncidentStatus[]
  /** Only those the owner gave this verdict of, `none` being those they gave none of. */
  verdicts?: readonly (VerdictKind | 'none')[]
  minSeverity?: Severity
  minConfidence?: number
  address?: string
  /** A search in words, such as `severity>=high source:wazuh -port:22`. */
  q?: string
  /** The time zone the person is in, for what `today` means in a search. */
  tz?: string
  /** Only incidents going on that are in one of these lanes. */
  lanes?: readonly Lane[]
  /** Only incidents of this kind. */
  family?: number
  limit?: number
  offset?: number
  /** `priority` puts the most serious and surest first; the default is the most recent. */
  order?: 'recent' | 'priority'
}

/** The incidents that match, the ones going most recently first unless asked for the most serious. */
export function fetchIncidents(query: IncidentQuery = {}): Promise<IncidentPage> {
  const params = new URLSearchParams()
  for (const status of query.statuses ?? []) params.append('status', status)
  for (const verdict of query.verdicts ?? []) params.append('verdict', verdict)
  if (query.minSeverity) params.set('min_severity', query.minSeverity)
  if (query.minConfidence) params.set('min_confidence', query.minConfidence.toString())
  if (query.address) params.set('address', query.address)
  if (query.q) params.set('q', query.q)
  if (query.tz) params.set('tz', query.tz)
  for (const lane of query.lanes ?? []) params.append('lane', lane)
  if (query.family) params.set('family', query.family.toString())
  if (query.limit !== undefined) params.set('limit', query.limit.toString())
  if (query.offset) params.set('offset', query.offset.toString())
  if (query.order) params.set('order', query.order)
  const search = params.toString()
  return apiGet<IncidentPage>(search ? `/incidents?${search}` : '/incidents')
}

/** One incident with the reasons for its confidence, its timeline and the devices in it. */
export function fetchIncident(id: number): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/incidents/${id.toString()}`)
}

/** Says what is being done about an incident, and returns it as it is now. */
export function setIncidentStatus(
  id: number,
  status: IncidentStatus,
  csrfToken: string,
): Promise<IncidentDetail> {
  return apiPatch<IncidentDetail>(`/incidents/${id.toString()}`, { status }, csrfToken)
}

/** What came of asking the AI about an incident. When it could not be asked (AI is off, no
 * provider is chosen, the provider failed) `ok` is false and `reason` says why in words; the
 * incident is there either way. */
export interface Triage {
  ok: boolean
  reason: string | null
  incident: IncidentDetail
}

/** Has the AI read the incident now, and returns it with what the AI made of it. It can take a
 * minute. */
export function askAi(id: number, csrfToken: string): Promise<Triage> {
  return apiPost<Triage>(`/incidents/${id.toString()}/triage`, undefined, csrfToken)
}

/** Which incidents a change is for: the ones that were picked, or all that a list of incidents
 * asked this way would show. */
export type BulkSelection = { ids: readonly number[] } | { matching: IncidentQuery }

/** What to change in all of them: what is being done about them, or what is thought of what they
 * are about (with a note, to say why). */
export type BulkChange = { status: IncidentStatus } | { verdict: VerdictKind; note?: string }

/** How to take a change back, as the change said it. */
export interface BulkUndo {
  /** The incidents it changed, by the status they had. */
  statuses: Partial<Record<IncidentStatus, number[]>>
  /** The verdicts it made, and what each said before (null if it is new). */
  rules: { id: number; replaced: VerdictKind | null }[]
}

/** What a change did, or with `preview` what it would do. */
export interface BulkResult {
  preview: boolean
  /** How many incidents it was about, and how many signals are in them. */
  incidents: number
  signals: number
  /** In how many of them it changes anything: the others already are so. */
  changed: number
  /** For a verdict, the incidents it could not be given on (no address and no alert), and how
   * many verdicts it makes or changes: one covers every incident about an address or alert. */
  skipped: number
  verdicts: number
  /** Null where nothing was changed, or where it was only asked about. */
  undo: BulkUndo | null
}

function matchingOf(query: IncidentQuery) {
  return {
    status: query.statuses ?? [],
    verdict: query.verdicts ?? [],
    ...(query.minSeverity ? { min_severity: query.minSeverity } : {}),
    min_confidence: query.minConfidence ?? 0,
    ...(query.address ? { address: query.address } : {}),
    ...(query.q ? { q: query.q } : {}),
    ...(query.tz ? { tz: query.tz } : {}),
    ...(query.lanes?.length ? { lane: query.lanes } : {}),
    ...(query.family ? { family: query.family } : {}),
  }
}

/** Changes many incidents in one go, all or none. With `preview` it only says what it would do. */
export function changeIncidents(
  selection: BulkSelection,
  change: BulkChange,
  csrfToken: string,
  preview = false,
): Promise<BulkResult> {
  const which =
    'ids' in selection ? { ids: selection.ids } : { matching: matchingOf(selection.matching) }
  return apiPost<BulkResult>(
    '/incidents/bulk',
    { ...which, ...change, ...(preview ? { preview } : {}) },
    csrfToken,
  )
}

/** Takes a change back, as it said how: how many incidents and verdicts that put right. */
export function undoChange(
  undo: BulkUndo,
  csrfToken: string,
): Promise<{ incidents: number; verdicts: number }> {
  return apiPost('/incidents/bulk/undo', undo, csrfToken)
}
