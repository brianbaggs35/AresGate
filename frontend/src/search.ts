/**
 * The search boxes, from the side of the person typing: the words of their languages to show as
 * help, how a term is taken out of the text or put into it, and the searches this browser
 * remembers. What a search means is decided by the API (`app/incidents/search.py` for incidents,
 * `app/events/search.py` for logs), which answers with the terms it understood; none of the
 * rules are repeated here.
 */
import type { SearchTerm, SourceCount } from '@/api/incidents'
import type { SearchScope } from '@/api/searches'
import { SEVERITIES, SEVERITY, type Severity } from '@/severity'

/** One way to search, as help. `text` is what it types into the box. */
export interface SearchExample {
  text: string
  meaning: string
}

/** What a search box is for: how it is named, what it hints at, how to search it and where the
 * searches made in it are remembered. */
export interface SearchKind {
  /** The page it is for, which the searches that are saved are kept under. */
  scope: SearchScope
  label: string
  placeholder: string
  examples: readonly SearchExample[]
  recentKey: string
}

export const SEARCH_EXAMPLES: readonly SearchExample[] = [
  { text: 'ssh', meaning: 'Words in the title, the address or what the strongest signal said' },
  { text: '"port scan"', meaning: 'Quotes keep words together' },
  { text: '203.0.113.7', meaning: 'An address that is in the incident' },
  { text: 'address:203.0.113.0/24', meaning: 'Any address in a range' },
  {
    text: 'source:wazuh',
    meaning: 'Reported by an integration: opnsense, ntopng, wazuh, crowdsec',
  },
  { text: 'severity>=high', meaning: 'At least this serious: info, low, medium, high, critical' },
  { text: 'confidence>=70', meaning: 'AresGate is at least this sure, 0 to 100' },
  { text: 'status:open,investigating', meaning: 'A comma gives choices' },
  {
    text: 'verdict:threat',
    meaning: 'What you said of it: threat, not suspicious, low priority, none',
  },
  { text: 'activity:scan', meaning: 'Scanning or brute force' },
  { text: 'signature:"ET SCAN"', meaning: 'A signal with this rule name' },
  { text: 'port:22', meaning: 'It touched this destination port' },
  { text: 'device:nas', meaning: 'It involves a device with this name, maker or hardware address' },
  { text: 'banned:yes', meaning: 'An integration banned the address' },
  {
    text: 'since:6h',
    meaning: 'Going on in the last 6h, 2d, 1w, or since today, yesterday or a date',
  },
  { text: 'before:2026-10-01', meaning: 'Began before a time' },
  { text: 'signals>=10', meaning: 'At least this many signals' },
  { text: '-source:wazuh', meaning: 'A minus in front turns any term around' },
]

export const RECENT_KEY = 'aresgate.incidents.searches'
export const LOG_RECENT_KEY = 'aresgate.logs.searches'

export const LOG_EXAMPLES: readonly SearchExample[] = [
  { text: 'failed', meaning: 'Words in what the event says or the rule that fired' },
  { text: '"failed password"', meaning: 'Quotes keep words together' },
  { text: '203.0.113.7', meaning: 'An address, from or to' },
  { text: 'address:203.0.113.0/24', meaning: 'Any address in a range' },
  { text: 'from:203.0.113.7', meaning: 'Only where it came from (to: is where it went)' },
  {
    text: 'source:opnsense',
    meaning: 'Reported by an integration: opnsense, ntopng, wazuh, crowdsec',
  },
  { text: 'severity>=high', meaning: 'At least this serious: info, low, medium, high, critical' },
  { text: 'kind:firewall', meaning: 'A kind of event, such as alert, firewall or decision' },
  { text: 'port:22,443', meaning: 'A destination port (sport: is the source port)' },
  { text: 'protocol:udp', meaning: 'The protocol, such as tcp, udp or icmp' },
  { text: 'signature:"ET SCAN"', meaning: 'Part of the rule that fired' },
  { text: 'raw:sshd', meaning: "Looks through the program's own record (slower: add a time)" },
  { text: 'incident:yes', meaning: 'Only events AresGate filed into an incident' },
  { text: 'since:1h', meaning: 'In the last 1h, 6h, 2d, 1w, or since today, yesterday or a date' },
  { text: 'before:2026-10-01', meaning: 'Before a time' },
  { text: '-source:ntopng', meaning: 'A minus in front turns any term around' },
]

export const INCIDENT_SEARCH: SearchKind = {
  scope: 'incidents',
  label: 'Search incidents',
  placeholder: 'severity>=high source:wazuh -port:22 ssh',
  examples: SEARCH_EXAMPLES,
  recentKey: RECENT_KEY,
}

export const LOG_SEARCH: SearchKind = {
  scope: 'logs',
  label: 'Search logs',
  placeholder: 'severity>=high source:opnsense -port:22 since:1h',
  examples: LOG_EXAMPLES,
  recentKey: LOG_RECENT_KEY,
}

/** The time zone this browser is in, such as America/Halifax, for what `today` means. */
export function zone(): string | undefined {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}

/** The text without one of its terms, and the space it leaves. */
export function without(text: string, { start, end }: Pick<SearchTerm, 'start' | 'end'>): string {
  const before = text.slice(0, start).trimEnd()
  const after = text.slice(end).trimStart()
  return before && after ? `${before} ${after}` : before + after
}

function pattern(term: string): RegExp {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)
  return new RegExp(String.raw`(^|\s)${escaped}(?=\s|$)`, 'gi')
}

/** Whether the text has this term, such as `severity:high`, written just so. */
export function hasTerm(text: string, term: string): boolean {
  return pattern(term).test(text)
}

/** One button of the summary under a search: a term that is added to the search or taken out. */
export interface FacetChoice {
  term: string
  label: string
  count: number
  on: boolean
  /** A theme color, for the severities. */
  color?: string
  icon?: (typeof SEVERITY)[Severity]['icon']
}

export interface FacetGroup {
  name: string
  choices: FacetChoice[]
}

/** The severities that have any, the most serious first. A choice nothing is left to match is not
 * offered, unless it is the one that made the list so short. */
export function severityChoices(
  counts: Readonly<Record<Severity, number>>,
  search: string,
): FacetChoice[] {
  return SEVERITIES.slice()
    .reverse()
    .map((level) => {
      const term = `severity:${level}`
      const { label, color, icon } = SEVERITY[level]
      return { term, label, count: counts[level], on: hasTerm(search, term), color, icon }
    })
    .filter(({ count, on }) => count > 0 || on)
}

/** The integrations, in the order the API gives them (the most first). */
export function sourceChoices(sources: readonly SourceCount[], search: string): FacetChoice[] {
  return sources.map(({ key, name, count }) => {
    const term = `source:${key}`
    return { term, label: name, count, on: hasTerm(search, term) }
  })
}

/** The kinds of event, in the order the API gives them (the most first). */
export function kindChoices(
  kinds: readonly { kind: string; count: number }[],
  search: string,
): FacetChoice[] {
  return kinds.map(({ kind, count }) => {
    const term = `kind:${kind}`
    return { term, label: kind, count, on: hasTerm(search, term) }
  })
}

/** The groups that have anything to choose from. */
export function groupsOf(...groups: FacetGroup[]): FacetGroup[] {
  return groups.filter(({ choices }) => choices.length > 0)
}

/** The text with the term put at its end, or taken out if it is there. */
export function toggled(text: string, term: string): string {
  if (hasTerm(text, term)) return text.replace(pattern(term), ' ').replace(/\s+/g, ' ').trim()
  return text.trim() ? `${text.trim()} ${term}` : term
}

/** What the views of the list have to give way to. A search that names a status or a verdict
 * is about those, whatever the list was showing: it looks across every status, and among the
 * incidents your verdicts quiet. */
export function impliedBy(text: string): { allStatuses: boolean; quieted: boolean } {
  const names = (field: string) => new RegExp(String.raw`(^|\s)-?${field}[:=]`, 'i').test(text)
  return { allStatuses: names('status'), quieted: names('verdict') }
}

export const MAX_RECENT = 8

/** The searches that were made in this browser, for the box that keeps them under `key`, the
 * newest first. */
export function readRecent(key: string): string[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(stored)) return []
    return (stored as unknown[])
      .filter((item): item is string => typeof item === 'string' && item.trim() !== '')
      .slice(0, MAX_RECENT)
  } catch {
    return []
  }
}

/** Remembers a search, in front of the others and once, and returns all that are remembered.
 * Where storage is off, the search is remembered until the page is closed. */
export function remember(text: string, key: string): string[] {
  const search = text.trim()
  const searches = readRecent(key)
  if (!search) return searches
  const kept = [search, ...searches.filter((item) => item !== search)].slice(0, MAX_RECENT)
  try {
    localStorage.setItem(key, JSON.stringify(kept))
  } catch {
    // Storage can be unavailable; the list still works for this visit.
  }
  return kept
}

export function forget(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // Nothing to take back if nothing could be kept.
  }
}
