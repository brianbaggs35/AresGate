import type { FlowNode } from '@/api/flow'
import {
  COLUMN_TITLES,
  DIRECTION_LABELS,
  DIRECTION_MEANINGS,
  WINDOW_LABELS,
  isOthers,
  layoutFlow,
  logSearch,
  neighbours,
  nodeLabel,
  nodeSummary,
  refusedShare,
  related,
  timelineBars,
} from '@/flow'
import { flow, node } from '@/test/flow'

const others = node({
  id: 'source:others',
  label: 'Others',
  scope: null,
  folded: 3,
  events: 3,
})
const service = (changes: Partial<FlowNode> = {}) =>
  node({
    id: 'service:tcp/443',
    column: 'service',
    label: 'tcp/443',
    scope: null,
    protocol: 'tcp',
    port: 443,
    ...changes,
  })

describe('what the picture says', () => {
  it('has a word for every window, direction and column', () => {
    expect(Object.keys(WINDOW_LABELS)).toEqual(['1', '6', '24', '168'])
    expect(DIRECTION_LABELS.outgoing).toBe('Leaving')
    expect(DIRECTION_MEANINGS.incoming).toBe('From the Internet to the home')
    expect(COLUMN_TITLES.service).toBe('To which service')
  })

  it('names a block: the address, the service as it is known, or how many it folds', () => {
    expect(nodeLabel(node())).toBe('192.168.1.20')
    expect(nodeLabel(service())).toBe('tcp/443 (HTTPS)')
    expect(nodeLabel(service({ protocol: null, port: 0, label: 'ip' }))).toBe('ip')
    expect(nodeLabel(service({ protocol: null, port: 22 }))).toBe('ip/22 (SSH)')
    expect(nodeLabel(others)).toBe('3 others')
    expect(isOthers(others)).toBe(true)
    expect(isOthers(node())).toBe(false)
  })

  it('sums a block up in a sentence', () => {
    expect(nodeSummary(node({ events: 7, blocked: 1 }))).toBe(
      'From 192.168.1.20: 7 connections, 1 refused',
    )
    expect(nodeSummary(node({ column: 'destination', events: 1 }))).toBe(
      'To 192.168.1.20: 1 connection',
    )
    expect(nodeSummary(service({ events: 2000, blocked: 0 }))).toBe(
      'Service tcp/443 (HTTPS): 2,000 connections',
    )
  })

  it('says what share was refused, none for nothing', () => {
    expect(refusedShare(8, 2)).toBe(25)
    expect(refusedShare(3, 1)).toBe(33)
    expect(refusedShare(0, 0)).toBe(0)
  })
})

describe('laying out the picture', () => {
  const data = flow()
  const layout = layoutFlow(data.nodes, data.links, 600, 300)
  const at = (id: string) => layout.nodes.find((placed) => placed.node.id === id)!

  it('puts the three columns at the left, middle and right, the busiest of each first', () => {
    expect(at('source:192.168.1.20').x).toBe(0)
    expect(at('service:tcp/443').x).toBe(294)
    expect(at('destination:93.184.216.34').x).toBe(588)
    expect(at('source:192.168.1.20').y).toBe(0)
    expect(at('source:8.8.8.8').y).toBeGreaterThan(at('source:192.168.1.20').height)
    expect(layout.nodes).toHaveLength(7)
  })

  it('makes a block as tall as what went through it, on one scale for every column', () => {
    const pixels = (id: string) => at(id).height / at(id).node.events
    expect(pixels('source:192.168.1.20')).toBeCloseTo(pixels('service:tcp/443'))
    expect(pixels('source:192.168.1.20')).toBeCloseTo(pixels('destination:192.168.1.20'))
  })

  it('keeps every column inside the height it was given', () => {
    for (const placed of layout.nodes) expect(placed.y + placed.height).toBeLessThanOrEqual(300.001)
  })

  it('draws a band for each link, with the refused part of it only where there was some', () => {
    expect(layout.ribbons).toHaveLength(6)
    const refused = layout.ribbons.filter(({ refused: part }) => part !== null)
    expect(refused.map(({ link }) => link.target).sort()).toEqual([
      'destination:192.168.1.20',
      'destination:93.184.216.34',
      'service:tcp/22',
      'service:tcp/25',
    ])
    expect(layout.ribbons[0]!.path).toMatch(/^M[\d.]+,[\d.]+ C.* Z$/)
  })

  it('stacks the bands that leave or reach a block one under the other', () => {
    const leaving = layout.ribbons.filter(({ link }) => link.source === 'source:192.168.1.20')
    const tops = leaving.map(({ path }) => Number(/^M[\d.]+,([\d.]+)/.exec(path)![1]))
    expect(new Set(tops).size).toBe(2)
  })

  it('gives the smallest block a height it can be pointed at', () => {
    const tiny = flow({
      nodes: [
        node({ events: 1000 }),
        node({ id: 'source:small', label: 'small', events: 1 }),
        service({ events: 1001 }),
        node({ id: 'destination:x', column: 'destination', events: 1001 }),
      ],
      links: [],
    })

    const placed = layoutFlow(tiny.nodes, tiny.links, 400, 200)

    expect(placed.nodes.find(({ node: found }) => found.id === 'source:small')!.height).toBe(6)
    const tall = placed.nodes.filter(({ node: found }) => found.column === 'source')
    const bottom = Math.max(...tall.map(({ y, height }) => y + height))
    expect(bottom).toBeLessThanOrEqual(200.001)
  })

  it('draws nothing, and does not divide by zero, for nothing', () => {
    expect(layoutFlow([], [], 400, 200)).toEqual({ nodes: [], ribbons: [] })
    const empty = layoutFlow([node({ events: 0 })], [], 400, 200)
    expect(empty.nodes[0]!.height).toBe(6)
  })

  it('leaves out a link whose block is not there', () => {
    const lonely = layoutFlow(
      [node()],
      [
        { source: 'source:192.168.1.20', target: 'nowhere', events: 1, blocked: 0 },
        { source: 'nobody', target: 'source:192.168.1.20', events: 1, blocked: 0 },
      ],
      400,
      200,
    )
    expect(lonely.ribbons).toEqual([])
  })

  it('finds what is on a path through a block', () => {
    expect(related('service:tcp/22', data.links)).toEqual(
      new Set(['service:tcp/22', 'source:8.8.8.8', 'destination:192.168.1.20']),
    )
    expect(related('lonely', data.links)).toEqual(new Set(['lonely']))
  })
})

describe('reading more of what a block stands for', () => {
  it('searches the logs for the firewall events of an address, from or to', () => {
    expect(logSearch(node(), 24)).toBe('kind:firewall since:24h from:192.168.1.20')
    expect(logSearch(node({ column: 'destination' }), 1)).toBe(
      'kind:firewall since:1h to:192.168.1.20',
    )
  })

  it('searches for a service by its protocol and port, and the week as 7d', () => {
    expect(logSearch(service(), 168)).toBe('kind:firewall since:7d protocol:tcp port:443')
    expect(logSearch(service({ protocol: null, port: 0 }), 6)).toBe('kind:firewall since:6h')
  })

  it('has no search for what is many things', () => {
    expect(logSearch(others, 24)).toBeNull()
  })

  it('lists what a block leads to, the biggest first, either side', () => {
    const data = flow()

    expect(
      neighbours('service:tcp/443', data).map(({ node: found, events }) => [found.id, events]),
    ).toEqual([
      ['destination:93.184.216.34', 6],
      ['source:192.168.1.20', 6],
    ])
    expect(neighbours('nothing', data)).toEqual([])
    expect(
      neighbours('destination:93.184.216.34', data).map(({ node: found }) => found.label),
    ).toEqual(['tcp/443', 'tcp/25'])
  })

  it('drops a link whose block is missing', () => {
    const data = flow({
      nodes: [node()],
      links: [{ source: 'source:192.168.1.20', target: 'x', events: 1, blocked: 0 }],
    })
    expect(neighbours('source:192.168.1.20', data)).toEqual([])
  })
})

describe('the timeline', () => {
  const data = flow()

  it('is a label, the allowed and the refused, and the stretch of each bar', () => {
    const bars = timelineBars(data.timeline, data.stride_seconds, 'en-US')

    expect(bars.categories).toHaveLength(24)
    expect(bars.categories[0]).toMatch(/\d{1,2}:00\s?[AP]M/)
    expect(bars.allowed.at(-1)).toBe(6)
    expect(bars.blocked.at(-1)).toBe(5)
    expect(bars.ranges[0]).toEqual({
      start: data.timeline[0]!.at,
      end: new Date(Date.parse(data.timeline[0]!.at) + 3_600_000).toISOString(),
    })
  })

  it('names the weekday once the window is longer than a day', () => {
    const bars = timelineBars(data.timeline, 21_600, 'en-US')

    expect(bars.categories[0]).toMatch(/^[A-Z][a-z]{2}/)
  })
})
