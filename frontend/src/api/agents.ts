import type { ChatCite } from '@/api/aiChat'
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'

/** What an agent is doing: going, waiting to go, doing nothing, or kept from running by itself. */
export type AgentState = 'running' | 'queued' | 'idle' | 'paused'

/** Where a run is, or how it ended. */
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** A kind of agent, which the owner makes one from. */
export interface Template {
  key: string
  name: string
  tagline: string
  description: string
  /** The name of an icon the web app knows (see `agents.ts`). */
  icon: string
  /** The instructions it starts with, which the owner may change. */
  goal: string
  /** How many minutes between runs to start with, or null to run only when started. */
  interval_minutes: number | null
  /** Whether it connects to devices on the network, which it only does once allowed and only
   * when started by hand. */
  active: boolean
  /** What it may look at, by the names of the tools the AI analyst has. */
  tools: string[]
}

/** One time an agent ran. */
export interface Run {
  id: number
  trigger: 'manual' | 'schedule'
  status: RunStatus
  requested_at: string
  started_at: string | null
  finished_at: string | null
  /** The step of the graph a running run is in. */
  node: string | null
  summary: string
  /** How many findings it has, and how serious the worst is. */
  findings: number
  worst: string | null
  rounds: number
  error: string | null
  /** Why the AI took no part, or empty if it did. */
  ai: string
}

export interface Agent {
  id: number
  name: string
  template: string
  template_name: string
  icon: string
  active: boolean
  goal: string
  enabled: boolean
  interval_minutes: number | null
  allow_active: boolean
  next_run_at: string | null
  created_at: string
  state: AgentState
  last_run: Run | null
  /** The outcomes of its last runs, oldest first. */
  recent: RunStatus[]
}

/** One arrow of the graph an agent runs. A conditional one is only followed sometimes. */
export interface Edge {
  source: string
  target: string
  conditional: boolean
}

export interface AgentDetail extends Agent {
  template_info: Template
  runs: Run[]
  graph: Edge[]
}

export interface Overview {
  agents: Agent[]
  templates: Template[]
  /** Why the AI would not be asked now, or null if it would be. Agents still collect without it. */
  ai: string | null
}

export interface Finding {
  severity: string
  title: string
  detail: string
  /** What it is based on that has a page of its own, as the chat names them. */
  cites: ChatCite[]
}

/** One thing a run did, for the owner to follow. */
export interface Step {
  seq: number
  at: string
  /** The step of the graph it belongs to: plan, act, think or report. */
  node: string
  title: string
  detail: Record<string, unknown>
}

export interface RunDetail extends Run {
  findings_list: Finding[]
  steps: Step[]
  call_ids: number[]
}

/** What the owner chooses for an agent. */
export interface AgentChoices {
  name: string
  goal: string
  interval_minutes: number | null
  enabled: boolean
  allow_active: boolean
}

const BASE = '/agents'

export const fetchAgents = () => apiGet<Overview>(BASE)

export const fetchAgent = (id: number) => apiGet<AgentDetail>(`${BASE}/${id}`)

export const createAgent = (template: string, choices: AgentChoices, csrfToken: string) =>
  apiPost<Agent>(BASE, { template, ...choices }, csrfToken)

export const changeAgent = (id: number, choices: AgentChoices, csrfToken: string) =>
  apiPut<Agent>(`${BASE}/${id}`, choices, csrfToken)

export const removeAgent = (id: number, csrfToken: string) => apiDelete(`${BASE}/${id}`, csrfToken)

export const startRun = (id: number, csrfToken: string) =>
  apiPost<Run>(`${BASE}/${id}/runs`, undefined, csrfToken)

export const fetchRun = (id: number, run: number) => apiGet<RunDetail>(`${BASE}/${id}/runs/${run}`)

export const cancelRun = (id: number, run: number, csrfToken: string) =>
  apiPost<Run>(`${BASE}/${id}/runs/${run}/cancel`, undefined, csrfToken)
