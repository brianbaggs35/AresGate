import { apiPost } from '@/api/client'

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
  /** Whether the answer was kept from an earlier check, so that no search was sent this time. */
  cached: boolean
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

/** Searches VirusTotal for an address, a domain or a web address. A subject checked within the last
 * week is answered from what AresGate kept, and no search is sent. Any other search counts toward the
 * limits of the access level, so one may be refused for a while (with the time to wait). */
export function searchThreatIntel(subject: string, csrfToken: string): Promise<Lookup> {
  return apiPost<Lookup>('/threat-intel/lookups', { subject }, csrfToken)
}
