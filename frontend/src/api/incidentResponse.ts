import { apiGet } from '@/api/client'
import type { IncidentStatus, ResponseState } from '@/api/incidents'
import type { Severity } from '@/severity'

/** The stretches of time the page can look back over. */
export type ResponseRange = '24h' | '7d' | '30d'

/** How many days each stretch is. */
export const RANGE_DAYS: Readonly<Record<ResponseRange, number>> = { '24h': 1, '7d': 7, '30d': 30 }

/** Where an incident goes, in the order the page shows them. */
export type ResponseGroupKey =
  'needs_response' | 'banned' | 'blocked' | 'ban_ended' | 'closed' | 'no_address'

/** One incident and what was done about it. */
export interface ResponseItem {
  id: number
  title: string
  /** The address it is about, or `rule:<integration>:<rule>` where it names none. */
  subject: string
  severity: Severity
  status: IncidentStatus
  last_seen_at: string
  state: ResponseState
  label: string
  /** Why it needs a response, for one that does. */
  why: string | null
  /** How many addresses are banned now, and how many it has to have banned. */
  banned_now: number
  attackers: number
  /** When the last of the bans runs out, or null when one doesn't say how long it lasts. */
  ban_ends_at: string | null
  /** How often the firewall turned the address away, and how many alerts Suricata stopped. */
  blocked: number
  dropped: number
}

export interface ResponseGroup {
  key: ResponseGroupKey
  label: string
  description: string
  /** All of them, the most serious first. */
  items: ResponseItem[]
}

export interface ResponseOverview {
  days: number
  /** How serious an incident has to be to be listed. */
  minimum: Severity
  /** How many there were in all, which is more than the groups hold past the limit. */
  total: number
  shown: number
  /** Without these, nothing can be seen of what the programs did. */
  crowdsec_connected: boolean
  opnsense_connected: boolean
  groups: ResponseGroup[]
}

export function fetchIncidentResponse(range: ResponseRange): Promise<ResponseOverview> {
  return apiGet<ResponseOverview>(`/incident-response?days=${RANGE_DAYS[range]}`)
}
