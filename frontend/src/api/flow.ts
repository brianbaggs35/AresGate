import { apiGet } from '@/api/client'

/** How far back the picture reaches, in hours: the last hour, six hours, day or week. */
export const FLOW_HOURS = [1, 6, 24, 168] as const
export type FlowHours = (typeof FLOW_HOURS)[number]

/** Which connections it shows: all of them, those that leave the home for the Internet, those that
 * come in from it, or those that stay between the home's own addresses. */
export const FLOW_DIRECTIONS = ['all', 'outgoing', 'incoming', 'inside'] as const
export type FlowDirection = (typeof FLOW_DIRECTIONS)[number]

export type FlowColumn = 'source' | 'service' | 'destination'

/** A block in one of the three columns: the address that connected, the service it asked for or
 * the address it reached. "Others" (`id` ends in `:others`) folds the ones too small to draw. */
export interface FlowNode {
  id: string
  column: FlowColumn
  label: string
  /** What an address on the Internet is called, when its reverse lookup is kept. */
  name: string | null
  scope: 'local' | 'outside' | null
  protocol: string | null
  /** 0 where a service has no port, and null for an address. */
  port: number | null
  events: number
  /** How many of them the firewall refused. */
  blocked: number
  /** How many nodes an "others" holds. */
  folded: number
}

/** The connections that went from one node to the next. */
export interface FlowLink {
  source: string
  target: string
  events: number
  blocked: number
}

/** The connections in one stretch of the window. */
export interface FlowBar {
  at: string
  allowed: number
  blocked: number
}

export interface Flow {
  hours: FlowHours
  direction: FlowDirection
  since: string
  until: string
  /** How wide each bar of the timeline is. */
  stride_seconds: number
  events: number
  blocked: number
  nodes: FlowNode[]
  links: FlowLink[]
  timeline: FlowBar[]
  /** Whether there were more paths than are read, so this is the busiest of them. */
  capped: boolean
}

export function fetchFlow(hours: FlowHours, direction: FlowDirection): Promise<Flow> {
  return apiGet<Flow>(`/flow?hours=${hours.toString()}&direction=${direction}`)
}
