/**
 * The search box, from the side of the person typing: the words of its language to show as help,
 * how a term is taken out of the text or put into it, and the searches this browser remembers.
 * What a search means is decided by the API (`app/incidents/search.py`), which answers with the
 * terms it understood; none of its rules are repeated here.
 */
import type { SearchTerm } from '@/api/incidents'

/** One way to search, as help. `text` is what it types into the box. */
export interface SearchExample {
  text: string
  meaning: string
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
  return new RegExp(`(^|\\s)${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?=\\s|$)`, 'gi')
}

/** Whether the text has this term, such as `severity:high`, written just so. */
export function hasTerm(text: string, term: string): boolean {
  return pattern(term).test(text)
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
  const names = (field: string) => new RegExp(`(^|\\s)-?${field}[:=]`, 'i').test(text)
  return { allStatuses: names('status'), quieted: names('verdict') }
}

export const RECENT_KEY = 'aresgate.incidents.searches'
export const MAX_RECENT = 8

/** The searches that were made in this browser, the newest first. */
export function readRecent(): string[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
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
export function remember(text: string): string[] {
  const search = text.trim()
  const searches = readRecent()
  if (!search) return searches
  const kept = [search, ...searches.filter((item) => item !== search)].slice(0, MAX_RECENT)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(kept))
  } catch {
    // Storage can be unavailable; the list still works for this visit.
  }
  return kept
}

export function forget(): void {
  try {
    localStorage.removeItem(RECENT_KEY)
  } catch {
    // Nothing to take back if nothing could be kept.
  }
}
