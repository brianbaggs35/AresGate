/**
 * The little of Discord's formatting a message of AresGate's uses, taken apart so that the page
 * can draw a message as Discord will without ever handing text to `v-html`: bold, code spans and
 * links (which are only the words of a link here, since a preview must not take anyone away).
 */

export interface Piece {
  kind: 'text' | 'bold' | 'code' | 'link'
  text: string
}

const TOKEN = /\*\*(?<bold>[^*]+)\*\*|`(?<code>[^`]+)`|\[(?<link>[^\]]+)\]\(https?:\/\/[^)\s]+\)/g
const KINDS = ['bold', 'code', 'link'] as const

/** One line of a message as pieces, in order. */
export function pieces(line: string): Piece[] {
  const found: Piece[] = []
  let from = 0
  for (const match of line.matchAll(TOKEN)) {
    if (match.index > from) found.push({ kind: 'text', text: line.slice(from, match.index) })
    for (const kind of KINDS) {
      const text = match.groups?.[kind]
      if (text !== undefined) found.push({ kind, text })
    }
    from = match.index + match[0].length
  }
  if (from < line.length) found.push({ kind: 'text', text: line.slice(from) })
  return found
}

/** A message's text as its lines, each as pieces. An empty line is a gap and has none. */
export function lines(text: string): Piece[][] {
  return text.split('\n').map(pieces)
}

/** A colour Discord takes as a number, as the `#rrggbb` a stylesheet takes. */
export function colorOf(color: number): string {
  return `#${(color & 0xffffff).toString(16).padStart(6, '0')}`
}
