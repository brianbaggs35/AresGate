import type { Flow, FlowBar, FlowLink, FlowNode } from '@/api/flow'

export function node(changes: Partial<FlowNode> = {}): FlowNode {
  return {
    id: 'source:192.168.1.20',
    column: 'source',
    label: '192.168.1.20',
    name: null,
    scope: 'local',
    protocol: null,
    port: null,
    events: 10,
    blocked: 0,
    folded: 0,
    ...changes,
  }
}

export function link(changes: Partial<FlowLink> = {}): FlowLink {
  return {
    source: 'source:192.168.1.20',
    target: 'service:tcp/443',
    events: 10,
    blocked: 0,
    ...changes,
  }
}

/** A laptop that reached a server on 443 (6 connections) and was refused on 25 (1), and a
 * scanner on the Internet refused on ssh (4), over a day of 24 bars. */
export function flow(changes: Partial<Flow> = {}): Flow {
  const timeline: FlowBar[] = Array.from({ length: 24 }, (_, hour) => ({
    at: new Date(Date.UTC(2026, 10, 15, hour)).toISOString(),
    allowed: hour === 23 ? 6 : 0,
    blocked: hour === 23 ? 5 : 0,
  }))
  return {
    hours: 24,
    direction: 'all',
    since: '2026-11-15T00:00:00Z',
    until: '2026-11-16T00:00:00Z',
    stride_seconds: 3600,
    events: 11,
    blocked: 5,
    nodes: [
      node({ events: 7, blocked: 1 }),
      node({
        id: 'source:8.8.8.8',
        label: '8.8.8.8',
        name: 'dns.example.net',
        scope: 'outside',
        events: 4,
        blocked: 4,
      }),
      node({
        id: 'service:tcp/443',
        column: 'service',
        label: 'tcp/443',
        scope: null,
        protocol: 'tcp',
        port: 443,
        events: 6,
        blocked: 0,
      }),
      node({
        id: 'service:tcp/25',
        column: 'service',
        label: 'tcp/25',
        scope: null,
        protocol: 'tcp',
        port: 25,
        events: 1,
        blocked: 1,
      }),
      node({
        id: 'service:tcp/22',
        column: 'service',
        label: 'tcp/22',
        scope: null,
        protocol: 'tcp',
        port: 22,
        events: 4,
        blocked: 4,
      }),
      node({
        id: 'destination:93.184.216.34',
        column: 'destination',
        label: '93.184.216.34',
        scope: 'outside',
        events: 7,
        blocked: 1,
      }),
      node({
        id: 'destination:192.168.1.20',
        column: 'destination',
        label: '192.168.1.20',
        scope: 'local',
        events: 4,
        blocked: 4,
      }),
    ],
    links: [
      link({ events: 6 }),
      link({ source: 'source:192.168.1.20', target: 'service:tcp/25', events: 1, blocked: 1 }),
      link({ source: 'source:8.8.8.8', target: 'service:tcp/22', events: 4, blocked: 4 }),
      link({ source: 'service:tcp/443', target: 'destination:93.184.216.34', events: 6 }),
      link({
        source: 'service:tcp/25',
        target: 'destination:93.184.216.34',
        events: 1,
        blocked: 1,
      }),
      link({ source: 'service:tcp/22', target: 'destination:192.168.1.20', events: 4, blocked: 4 }),
    ],
    timeline,
    capped: false,
    ...changes,
  }
}
