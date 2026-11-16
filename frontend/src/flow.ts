import type {
  Flow,
  FlowBar,
  FlowColumn,
  FlowDirection,
  FlowHours,
  FlowLink,
  FlowNode,
} from '@/api/flow'
import { portLabel } from '@/incidents'
import { formatCount } from '@/format'

export const WINDOW_LABELS: Readonly<Record<FlowHours, string>> = {
  1: 'Hour',
  6: '6 hours',
  24: 'Day',
  168: 'Week',
}

export const DIRECTION_LABELS: Readonly<Record<FlowDirection, string>> = {
  all: 'All',
  outgoing: 'Leaving',
  incoming: 'Arriving',
  inside: 'Inside',
}

/** What the direction means, for a title that is read on hover and by a screen reader. */
export const DIRECTION_MEANINGS: Readonly<Record<FlowDirection, string>> = {
  all: 'Every connection the firewall wrote down',
  outgoing: 'From the home to the Internet',
  incoming: 'From the Internet to the home',
  inside: 'Between the home’s own addresses',
}

export const COLUMN_TITLES: Readonly<Record<FlowColumn, string>> = {
  source: 'Who connected',
  service: 'To which service',
  destination: 'What it reached',
}

export const isOthers = (node: Pick<FlowNode, 'id'>) => node.id.endsWith(':others')

/** What a node is called on the picture: an address, a service with its well-known name, or
 * "N others". */
export function nodeLabel(node: FlowNode): string {
  if (isOthers(node)) return `${formatCount(node.folded)} others`
  if (node.column === 'service' && node.port) {
    return `${node.protocol ?? 'ip'}/${portLabel(node.port)}`
  }
  return node.label
}

const KIND_WORDS: Record<FlowColumn, string> = {
  source: 'From',
  service: 'Service',
  destination: 'To',
}

/** A node in a sentence for a screen reader: what it is, how much went through it, how much of
 * that was refused. */
export function nodeSummary(node: FlowNode): string {
  const kind = KIND_WORDS[node.column]
  const refused = node.blocked > 0 ? `, ${formatCount(node.blocked)} refused` : ''
  const count = node.events === 1 ? '1 connection' : `${formatCount(node.events)} connections`
  return `${kind} ${nodeLabel(node)}: ${count}${refused}`
}

/** The share of connections that were refused, as a whole percent. */
export function refusedShare(events: number, blocked: number): number {
  return events === 0 ? 0 : Math.round((blocked / events) * 100)
}

// ---------------------------------------------------------------------------------------------
// The picture

export interface Placed {
  node: FlowNode
  x: number
  y: number
  width: number
  height: number
}

export interface Ribbon {
  link: FlowLink
  /** The whole band, and the part of it that was refused (null where none was). */
  path: string
  refused: string | null
}

export interface Layout {
  nodes: Placed[]
  ribbons: Ribbon[]
}

/** The least a node is tall, so that the smallest is still something to point at. */
const MIN_HEIGHT = 6
const GAP = 10

export const COLUMNS: readonly FlowColumn[] = ['source', 'service', 'destination']

function band(x0: number, y0: number, x1: number, y1: number, thickness: number): string {
  const middle = (x0 + x1) / 2
  return [
    `M${x0},${y0}`,
    `C${middle},${y0} ${middle},${y1} ${x1},${y1}`,
    `L${x1},${y1 + thickness}`,
    `C${middle},${y1 + thickness} ${middle},${y0 + thickness} ${x0},${y0 + thickness}`,
    'Z',
  ].join(' ')
}

/** How many connections one pixel of height stands for, the same for every column, so that a
 * band is as thick where it leaves one block as where it arrives at the next. */
function scaleFor(columns: readonly (readonly FlowNode[])[], height: number): number {
  let scale = Infinity
  for (const nodes of columns) {
    const total = nodes.reduce((sum, { events }) => sum + events, 0)
    if (total === 0) continue
    const room = height - GAP * Math.max(0, nodes.length - 1)
    const small = nodes.filter((node) => (node.events * room) / total < MIN_HEIGHT).length
    // What the small ones are given beyond their share is taken from the rest.
    const left = Math.max(1, room - small * MIN_HEIGHT)
    const rest = nodes.reduce(
      (sum, node) => ((node.events * room) / total < MIN_HEIGHT ? sum : sum + node.events),
      0,
    )
    scale = Math.min(scale, left / Math.max(rest, 1))
  }
  return Number.isFinite(scale) ? scale : 1
}

/** Where each block and each band goes in a picture `width` wide and `height` tall: three
 * columns, busiest first from the top, each band as thick as the connections it carries, and
 * the refused part of a band drawn along its top edge. */
export function layoutFlow(
  nodes: readonly FlowNode[],
  links: readonly FlowLink[],
  width: number,
  height: number,
  blockWidth = 12,
): Layout {
  const columns = COLUMNS.map((column) => nodes.filter((node) => node.column === column))
  const scale = scaleFor(columns, height)
  const placed = new Map<string, Placed>()
  const across: Record<FlowColumn, number> = {
    source: 0,
    service: (width - blockWidth) / 2,
    destination: width - blockWidth,
  }
  columns.forEach((members, index) => {
    const x = across[COLUMNS[index] as FlowColumn]
    let y = 0
    for (const node of members) {
      const tall = Math.max(MIN_HEIGHT, node.events * scale)
      placed.set(node.id, { node, x, y, width: blockWidth, height: tall })
      y += tall + GAP
    }
  })

  const out = new Map<string, number>()
  const into = new Map<string, number>()
  const joined = links.flatMap((link) => {
    const from = placed.get(link.source)
    const to = placed.get(link.target)
    return from && to ? [{ link, from, to }] : []
  })
  joined.sort((a, b) => a.to.y - b.to.y || a.from.y - b.from.y)
  const ribbons: Ribbon[] = []
  for (const { link, from, to } of joined) {
    const thick = Math.max(1, link.events * scale)
    const refused = link.blocked * scale
    const y0 = from.y + (out.get(link.source) ?? 0)
    const y1 = to.y + (into.get(link.target) ?? 0)
    out.set(link.source, (out.get(link.source) ?? 0) + thick)
    into.set(link.target, (into.get(link.target) ?? 0) + thick)
    const x0 = from.x + from.width
    ribbons.push({
      link,
      path: band(x0, y0, to.x, y1, thick),
      refused:
        link.blocked > 0 ? band(x0, y0, to.x, y1, Math.min(thick, Math.max(1, refused))) : null,
    })
  }
  return { nodes: [...placed.values()], ribbons }
}

/** The ids of what is on a path through `id`: the block, the bands that touch it and the blocks
 * at their other ends. */
export function related(id: string, links: readonly FlowLink[]): Set<string> {
  const ids = new Set([id])
  for (const link of links) {
    if (link.source === id || link.target === id) {
      ids.add(link.source)
      ids.add(link.target)
    }
  }
  return ids
}

// ---------------------------------------------------------------------------------------------
// Reading more of what a block stands for

/** The Logs search for the connections a block stands for, over the window: the same firewall
 * events the picture was made of. Null for "others", which stands for no one thing. */
export function logSearch(node: FlowNode, hours: FlowHours): string | null {
  if (isOthers(node)) return null
  const within = hours === 168 ? 'since:7d' : `since:${hours.toString()}h`
  const base = `kind:firewall ${within}`
  if (node.column === 'service') {
    const port = node.port ? ` port:${node.port.toString()}` : ''
    const protocol = node.protocol ? ` protocol:${node.protocol}` : ''
    return `${base}${protocol}${port}`
  }
  return `${base} ${node.column === 'source' ? 'from' : 'to'}:${node.label}`
}

function otherEnd(link: FlowLink, id: string): string | null {
  if (link.source === id) return link.target
  return link.target === id ? link.source : null
}

/** The blocks a block's bands lead to, the biggest first, with how much each carried. */
export function neighbours(
  id: string,
  flow: Pick<Flow, 'nodes' | 'links'>,
): { node: FlowNode; events: number; blocked: number }[] {
  const byId = new Map(flow.nodes.map((node) => [node.id, node]))
  const found: { node: FlowNode; events: number; blocked: number }[] = []
  for (const link of flow.links) {
    const other = otherEnd(link, id)
    const node = other ? byId.get(other) : undefined
    if (node) found.push({ node, events: link.events, blocked: link.blocked })
  }
  return found.sort((a, b) => b.events - a.events || a.node.id.localeCompare(b.node.id))
}

// ---------------------------------------------------------------------------------------------
// The timeline

export interface Bars {
  categories: string[]
  allowed: number[]
  blocked: number[]
  /** The stretch each bar stands for, as the Logs search takes it. */
  ranges: { start: string; end: string }[]
}

/** The timeline as the chart takes it: a label, the allowed and the refused for each bar. */
export function timelineBars(
  timeline: readonly FlowBar[],
  strideSeconds: number,
  locale?: string,
): Bars {
  const days = strideSeconds * timeline.length > 86_400
  const label = new Intl.DateTimeFormat(
    locale,
    days
      ? { weekday: 'short', hour: 'numeric', minute: '2-digit' }
      : { hour: 'numeric', minute: '2-digit' },
  )
  return {
    categories: timeline.map(({ at }) => label.format(new Date(at))),
    allowed: timeline.map(({ allowed }) => allowed),
    blocked: timeline.map(({ blocked }) => blocked),
    ranges: timeline.map(({ at }) => ({
      start: at,
      end: new Date(Date.parse(at) + strideSeconds * 1000).toISOString(),
    })),
  }
}
