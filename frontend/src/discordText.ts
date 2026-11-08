/**
 * The little of Discord's formatting a message of AresGate's uses, taken apart so that the page
 * can draw a message as Discord will without ever handing text to `v-html`: bold, code spans and
 * links (which are only the words of a link here, since a preview must not take anyone away).
 * It looks for each closing mark with `indexOf` rather than a pattern, so that a line with marks
 * that never close is read once, not once for each of them.
 */

export interface Piece {
  kind: 'text' | 'bold' | 'code' | 'link'
  text: string
}

/** Where a link may go: only the web, with no spaces in it. */
const WEB = /^https?:\/\/\S+$/

interface Taken {
  piece: Piece
  /** Where the line goes on after it. */
  next: number
}

/** What is between the mark at `at` and the next `close`, if there is something and it is closed. */
function between(line: string, at: number, open: number, close: string): [string, number] | null {
  const end = line.indexOf(close, at + open)
  return end > at + open ? [line.slice(at + open, end), end + close.length] : null
}

/** The bold, code or link that starts at `at`, or none if what is there is only words. */
function take(line: string, at: number): Taken | null {
  if (line.startsWith('**', at)) {
    const found = between(line, at, 2, '**')
    return found && { piece: { kind: 'bold', text: found[0] }, next: found[1] }
  }
  if (line[at] === '`') {
    const found = between(line, at, 1, '`')
    return found && { piece: { kind: 'code', text: found[0] }, next: found[1] }
  }
  if (line[at] === '[') {
    const found = between(line, at, 1, '](')
    if (!found) return null
    const end = line.indexOf(')', found[1])
    if (end === -1 || !WEB.test(line.slice(found[1], end))) return null
    return { piece: { kind: 'link', text: found[0] }, next: end + 1 }
  }
  return null
}

/** One line of a message as pieces, in order. */
export function pieces(line: string): Piece[] {
  const found: Piece[] = []
  let words = ''
  let at = 0
  while (at < line.length) {
    const taken = take(line, at)
    if (taken) {
      if (words) found.push({ kind: 'text', text: words })
      found.push(taken.piece)
      words = ''
      at = taken.next
    } else {
      words += line.charAt(at)
      at += 1
    }
  }
  if (words) found.push({ kind: 'text', text: words })
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
