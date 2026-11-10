import { apiGet, apiPost } from '@/api/client'

/** What a search is about: an internet address, a domain, or a web address. */
export type SubjectKind = 'ip' | 'domain' | 'url'

/** What VirusTotal makes of the subject, from the counts of its engines. */
export type Judgement = 'malicious' | 'suspicious' | 'clean' | 'unknown'

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
  judgement: Judgement
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
