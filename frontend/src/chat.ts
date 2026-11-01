import type { RouteLocationRaw } from 'vue-router'

import type { ChatCite } from '@/api/aiChat'

/** What to try asking, for a page with nothing said on it yet. */
export const STARTERS: readonly string[] = [
  'What needs my attention right now?',
  'Is anything on my network behaving oddly?',
  'Are all my integrations working?',
  'Which addresses did the firewall block the most today?',
]

/** The longest a question may be, as the API holds it. */
export const MAX_QUESTION = 2000

/** Where a thing an answer cites is, or null for one with no page of its own. */
export function citeRoute(cite: ChatCite): RouteLocationRaw | null {
  if (cite.kind === 'incident') return { name: 'incident', params: { id: cite.key } }
  if (cite.kind === 'integration') return { name: 'integration', params: { key: cite.key } }
  return null
}

/** The question the "Ask the assistant" button on a page starts with, from what it is about
 * (`incident:3`), or null for anything else. The person reads it and presses Send. */
export function questionAbout(about: string | null | undefined): string | null {
  const found = /^incident:(\d{1,18})$/.exec(about ?? '')
  return found
    ? `What should I know about incident ${found[1]}, and what should I do about it?`
    : null
}

/** One piece of an answer's text: words, or an incident to link to. */
export type Piece = { text: string } | { incident: number }

/** The text of an answer cut into words and the incidents it names as [incident 3], which the
 * page turns into links. */
export function pieces(text: string): Piece[] {
  const found: Piece[] = []
  let from = 0
  for (const match of text.matchAll(/\[incident (\d{1,18})\]/g)) {
    if (match.index > from) found.push({ text: text.slice(from, match.index) })
    found.push({ incident: Number(match[1]) })
    from = match.index + match[0].length
  }
  if (from < text.length) found.push({ text: text.slice(from) })
  return found
}

/** A block of an answer: a paragraph, or a list. */
export type Block = { paragraph: string } | { items: string[] }

/** An answer cut into paragraphs (split by blank lines) and lists (lines that begin with - or *),
 * so that it reads as it was written without the page having to understand markdown. */
export function blocks(text: string): Block[] {
  const found: Block[] = []
  let items: string[] = []
  const flush = () => {
    if (items.length > 0) found.push({ items })
    items = []
  }
  let paragraph: string[] = []
  const close = () => {
    if (paragraph.length > 0) found.push({ paragraph: paragraph.join(' ') })
    paragraph = []
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (/^[-*•]\s/.test(line)) {
      close()
      items.push(line.slice(1).trim())
    } else if (line === '') {
      close()
      flush()
    } else {
      flush()
      paragraph.push(line)
    }
  }
  close()
  flush()
  return found
}
