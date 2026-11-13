import type { ChatCite } from '@/api/aiChat'
import type { UsageLimit } from '@/api/aiUsage'
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'

/** What an agent is doing: going, waiting to go, doing nothing, or kept from running by itself. */
export type AgentState = 'running' | 'queued' | 'idle' | 'paused'

/** Where a run is, or how it ended. */
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** One thing a kind of agent needs, such as an integration, and whether it is there. */
export interface Check {
  key: string
  ok: boolean
  text: string
  /** What to do when it is missing, and where in the web app to do it. */
  fix: string
  link: string
}

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
  /** What it needs to be useful, and whether each is there. */
  checks: Check[]
  ready: boolean
  /** The steps to set it up, for someone making one for the first time. */
  setup: string[]
  /** Whether it suggests changes for the owner to approve, as the cleanup agent does. */
  proposes: boolean
}

/** What agents asked of the AI and what it cost: the money is in millionths of a US dollar, the
 * tokens in the cache are counted apart from the rest, and a request to a model whose price isn't
 * known is counted but not priced. */
export interface Usage {
  runs: number
  calls: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  cost_micros: number
  unpriced_calls: number
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
  /** How many findings there are of each severity, for those there are any of. */
  by_severity: Record<string, number>
  rounds: number
  error: string | null
  /** Why the AI took no part, or empty if it did. */
  ai: string
  /** What it used of the AI, and who answered last (none if nobody was asked). */
  usage: Usage
  provider: string | null
  model: string | null
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
  /** What it used of the AI over the last 30 days. */
  usage: Usage
  /** How many of its suggestions wait for the owner. */
  proposals: number
}

/** Where a suggestion of the cleanup agent is. */
export type ProposalStatus = 'pending' | 'applied' | 'dismissed' | 'undone'

/** Something the cleanup agent suggests tidying, and what became of it. */
export interface Proposal {
  id: number
  agent_id: number
  agent_name: string
  /** `duplicates`, `stale` or `benign`. */
  kind: string
  title: string
  detail: string
  /** What is done to the incidents: `dismiss`, `resolve` or `not_suspicious`. */
  action: string
  incident_ids: number[]
  /** The incident that stays when the rest of a group of duplicates is dismissed. */
  keep_id: number | null
  confidence: number
  status: ProposalStatus
  decided_by: 'owner' | 'agent' | null
  created_at: string
  decided_at: string | null
}

export interface ProposalList {
  pending: Proposal[]
  recent: Proposal[]
}

/** One day of what an agent used of the AI. */
export interface UsageDay {
  /** The date, UTC, as `2026-11-10`. */
  day: string
  runs: number
  tokens: number
  cost_micros: number
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
  /** Each of the last 30 days, oldest first. */
  days: UsageDay[]
  /** What it suggests tidying, and what was decided lately. */
  suggestions: ProposalList
}

/** One finding of an agent's last run that is worth the owner's time. */
export interface AttentionItem {
  agent_id: number
  agent_name: string
  icon: string
  run_id: number
  finished_at: string
  severity: string
  title: string
  detail: string
  action: string
  status: 'new' | 'ongoing'
}

/** What the daily briefing agent said the last time it finished. */
export interface Briefing {
  agent_id: number
  agent_name: string
  run_id: number
  finished_at: string
  summary: string
}

export interface Overview {
  agents: Agent[]
  templates: Template[]
  /** Why the AI would not be asked now, or null if it would be. Agents still collect without it. */
  ai: string | null
  /** What all the agents used of the AI over the last 30 days, and the limits on what they spend. */
  usage: Usage
  limits: UsageLimit[]
  /** How many suggestions of the cleanup agent wait for the owner. */
  proposals: number
  /** What the agents together say needs the owner, the most serious first, and how many there
   * are in all. */
  attention: AttentionItem[]
  attention_total: number
  /** The latest daily briefing, if an agent writes one. */
  briefing: Briefing | null
}

export interface Finding {
  severity: string
  title: string
  detail: string
  /** What it is based on that has a page of its own, as the chat names them. */
  cites: ChatCite[]
  /** Whether the agent's last run reported the same thing. */
  status: 'new' | 'ongoing'
  /** The one thing to do about it, or empty when there is nothing to do. */
  action: string
  /** How sure the agent is, given what it was shown. */
  confidence: 'low' | 'medium' | 'high'
  /** Since when it has been reported, and in how many runs in a row. */
  first_seen_at: string
  runs_seen: number
  /** The facts it rests on, one to a line; how to check it for yourself; what would make it
   * harmless. Empty for a finding made before they were asked for, or when the agent was not shown
   * enough to say. */
  evidence: string[]
  verify: string
  benign: string
}

/** A finding the run before reported and this one does not. */
export interface Gone {
  severity: string
  title: string
}

/** How a run differs from the one before it that finished well. */
export interface Changes {
  since: string
  gone: Gone[]
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
  /** Null for a run that did not finish well, and for the first one. */
  changes: Changes | null
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

/** Where the agents get their AI: what Settings > AI chose, a provider of their own, or none. */
export type AiSource = 'shared' | 'own' | 'off'

/** What the cleanup agent does with what it finds. */
export type CleanupMode = 'suggest' | 'auto'

/** Who the agents ask now, and whether that charges by the token. */
export interface Asking {
  provider: string
  label: string
  model: string
  charges: boolean
}

export interface AgentSettings {
  ai_source: AiSource
  provider: string | null
  model: string | null
  /** Whether the cleanup agent only suggests tidying, or does the surest of it too. */
  cleanup_mode: CleanupMode
  /** Who they ask now, or null and why not. */
  asking: Asking | null
  reason: string | null
  limits: UsageLimit[]
}

/** What the owner chooses for the agents' use of the AI. The limits are in dollars. */
export interface AgentSettingsChoices {
  ai_source: AiSource
  provider: string | null
  model: string | null
  daily: string | null
  monthly: string | null
  /** Left out, it stays as it was. */
  cleanup_mode?: CleanupMode
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

export const fetchAgentSettings = () => apiGet<AgentSettings>(`${BASE}/settings`)

export const saveAgentSettings = (choices: AgentSettingsChoices, csrfToken: string) =>
  apiPut<AgentSettings>(`${BASE}/settings`, choices, csrfToken)

export const fetchProposals = () => apiGet<ProposalList>(`${BASE}/proposals`)

export const applyProposal = (id: number, csrfToken: string) =>
  apiPost<Proposal>(`${BASE}/proposals/${id}/apply`, undefined, csrfToken)

export const dismissProposal = (id: number, csrfToken: string) =>
  apiPost<Proposal>(`${BASE}/proposals/${id}/dismiss`, undefined, csrfToken)

export const undoProposal = (id: number, csrfToken: string) =>
  apiPost<Proposal>(`${BASE}/proposals/${id}/undo`, undefined, csrfToken)
