import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'

/** What a search is about: an internet address, a domain, or a web address. */
export type SubjectKind = 'ip' | 'domain' | 'url'

/** What VirusTotal makes of the subject, from the counts of its engines. */
export type Judgement = 'malicious' | 'suspicious' | 'clean' | 'unknown'

/** What the owner of the network says of a subject, whatever the services made of it. */
export type Verdict = 'safe' | 'suspicious'

/** What the owner ruled of a subject: it corrects a false positive or a false negative. */
export interface Ruling {
  kind: SubjectKind
  /** The subject as it is shown: the address, the domain, or the host of a web address. */
  subject: string
  verdict: Verdict
  note: string | null
  /** When it was ruled. */
  set_at: string
  /** What the ruling comes to, on the scale of a judgement. */
  judgement: Judgement
}

/** What is known of a ruling where it was not read as one: what was ruled, and why. */
export type Ruled = Pick<Ruling, 'verdict' | 'note'> & Partial<Pick<Ruling, 'set_at'>>

/** One thing VirusTotal says beyond the counts, such as who owns an address. */
export interface Detail {
  label: string
  value: string
}

/** What VirusTotal reported of a search, with the counts its judgement is made from. */
export interface Lookup {
  kind: SubjectKind
  /** The subject as it was searched for. */
  subject: string
  /** What it comes to: the owner's ruling where there is one, else what VirusTotal made of it. */
  judgement: Judgement
  /** What VirusTotal made of it, which a ruling does not change. */
  reported_judgement: Judgement
  /** What the owner ruled of it, or null if they did not. */
  ruling: Ruling | null
  /** When AresGate asked VirusTotal about the subject. */
  checked_at: string
  /** Whether the answer was kept from an earlier check, so that none came from VirusTotal now. */
  cached: boolean
  /** Whether the answer is past the time it is taken as fresh for. */
  stale: boolean
  /** Why the answer kept could not be checked again, if a search tried to and could not. */
  notice: string | null
  /** Whether searching for the subject asks about this again. A kept web address is kept without
   * its text, so it can't be. */
  repeatable: boolean
  /** When AresGate first asked about the subject, and how many answers it has had since. */
  first_checked_at: string
  checks: number
  /** When the answer stops being taken as fresh, so the subject is asked about again. */
  fresh_until: string
  /** When a newer answer last changed the judgement, and what it was before. */
  changed_at: string | null
  previous_judgement: Judgement | null
  /** When the subject was last analysed, as VirusTotal says, or null if it has no report. */
  analysed_at: string | null
  malicious: number
  suspicious: number
  harmless: number
  undetected: number
  /** The community's score: below zero leans malicious, above zero leans harmless. */
  reputation: number | null
  categories: string[]
  details: Detail[]
  /** The subject's page on VirusTotal's own website. */
  link: string
}

/** Searches VirusTotal for an address, a domain or a web address. A subject whose answer is still
 * fresh is answered from what AresGate kept, and no search is sent, unless `refresh` asks for one.
 * Any other search counts toward the limits of the access level. One that a limit holds is answered
 * from what was kept, with a notice, or refused (with the time to wait) if nothing is kept. */
export function searchThreatIntel(
  subject: string,
  csrfToken: string,
  refresh = false,
): Promise<Lookup> {
  return apiPost<Lookup>(
    '/threat-intel/lookups',
    refresh ? { subject, refresh } : { subject },
    csrfToken,
  )
}

/** How many answers are kept of each judgement. */
export type KnownCounts = Record<Judgement, number>

/** One page of the answers AresGate has kept, newest first. */
export interface KnownPage {
  /** How many answers match, of which `items` is one page. */
  total: number
  /** How many match of each judgement, whichever judgement was asked for. */
  counts: KnownCounts
  items: Lookup[]
}

export interface KnownQuery {
  /** Part of an address, a name or an owner. */
  q?: string
  kind?: SubjectKind | null
  judgement?: Judgement | null
  limit?: number
  offset?: number
}

/** The answers AresGate has kept. Reading them asks VirusTotal nothing. */
export function fetchKnownThreats(query: KnownQuery = {}): Promise<KnownPage> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.kind) params.set('kind', query.kind)
  if (query.judgement) params.set('judgement', query.judgement)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset) params.set('offset', String(query.offset))
  const search = params.toString()
  return apiGet<KnownPage>(search ? `/threat-intel/subjects?${search}` : '/threat-intel/subjects')
}

/** Everything the owner has ruled on, the latest first, whether or not a service has answered. */
export function fetchRulings(): Promise<{ items: Ruling[] }> {
  return apiGet<{ items: Ruling[] }>('/threat-intel/overrides')
}

/** Rules a subject safe or suspicious, in place of any ruling there was. Nothing is sent to a
 * service, so any address, domain or web address on the internet can be ruled on. */
export function ruleOnThreat(
  subject: string,
  verdict: Verdict,
  note: string | null,
  csrfToken: string,
): Promise<Ruling> {
  return apiPut<Ruling>('/threat-intel/overrides', { subject, verdict, note }, csrfToken)
}

/** Takes back what the owner ruled of a subject, so it is what the services made of it again. */
export function takeBackRuling(subject: string, csrfToken: string): Promise<undefined> {
  return apiDelete(`/threat-intel/overrides?subject=${encodeURIComponent(subject)}`, csrfToken)
}
