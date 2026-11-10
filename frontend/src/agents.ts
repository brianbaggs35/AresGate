import {
  Ban,
  Bot,
  Brain,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  Clock,
  Eye,
  FileText,
  HeartPulse,
  ListChecks,
  LoaderCircle,
  Pause,
  Radar,
  ScanSearch,
  Telescope,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Agent, AgentState, Edge, Run, RunStatus, Step } from '@/api/agents'
import { formatCount } from '@/format'
import { SEVERITIES, type Severity } from '@/severity'

type Icon = NonNullable<IconProps['icon']>

/** The icon of each kind of agent, by the name the API gives it. */
const ICONS: Readonly<Record<string, Icon>> = {
  radar: Radar,
  telescope: Telescope,
  'heart-pulse': HeartPulse,
  'scan-search': ScanSearch,
}

/** The icon for a kind of agent, and a robot for one that this version doesn't know. */
export const agentIcon = (name: string): Icon => ICONS[name] ?? Bot

/** What each step of an agent's run is called, and what it does, for the graph and the timeline.
 * They are the nodes of the LangGraph graph the backend runs, in the order it runs them. */
export interface NodeInfo {
  id: string
  label: string
  hint: string
  icon: Icon
}

export const NODES: readonly NodeInfo[] = [
  { id: 'plan', label: 'Plan', hint: 'Decides what to look at first', icon: ListChecks },
  { id: 'act', label: 'Look', hint: 'Reads what AresGate knows', icon: Eye },
  { id: 'think', label: 'Think', hint: 'Asks the AI what it makes of it', icon: Brain },
  { id: 'report', label: 'Report', hint: 'Settles what it found', icon: FileText },
]

/** The most times the agent looks and thinks in a run, which the backend enforces. */
export const MAX_ROUNDS = 3

export const nodeInfo = (id: string): NodeInfo =>
  NODES.find((node) => node.id === id) ?? { id, label: id, hint: '', icon: CircleDashed }

/** The nodes of the graph the API described, in the order they run, and the arrows that go back
 * to an earlier one, which are the loop of looking again. */
export function shape(edges: readonly Edge[]): { nodes: NodeInfo[]; loops: Edge[] } {
  const named = new Set(edges.flatMap((edge) => [edge.source, edge.target]))
  const nodes = NODES.filter((node) => named.has(node.id))
  const order = (id: string) => nodes.findIndex((node) => node.id === id)
  const loops = edges.filter((edge) => order(edge.target) < order(edge.source))
  return { nodes, loops }
}

/** Where a step of the graph is in a run: waiting for its turn, going now, done, or never
 * reached because the run ended first. */
export type NodeState = 'waiting' | 'active' | 'done' | 'skipped'

export function nodeState(
  id: string,
  run: Pick<Run, 'status' | 'node'> | null,
  steps: readonly Pick<Step, 'node'>[],
): NodeState {
  if (!run) return 'waiting'
  const seen = steps.some((step) => step.node === id)
  if (run.status === 'running' && run.node === id) return 'active'
  if (seen) return 'done'
  return run.status === 'queued' || run.status === 'running' ? 'waiting' : 'skipped'
}

/** Whether a run is waiting for the worker or going, so that what is shown of it changes. */
export const isLive = (run: Pick<Run, 'status'> | null | undefined): boolean =>
  run?.status === 'queued' || run?.status === 'running'

export const anyLive = (agents: readonly Pick<Agent, 'state'>[]): boolean =>
  agents.some((agent) => agent.state === 'running' || agent.state === 'queued')

interface Look {
  label: string
  /** A theme color. */
  color: string
  icon: Icon
}

/** Never just a color: each status has its own icon and its name. */
export const RUN_STATUS: Readonly<Record<RunStatus, Look>> = {
  queued: { label: 'Waiting to start', color: 'info', icon: Clock },
  running: { label: 'Running', color: 'primary', icon: LoaderCircle },
  succeeded: { label: 'Finished', color: 'success', icon: CircleCheck },
  failed: { label: 'Failed', color: 'error', icon: CircleAlert },
  cancelled: { label: 'Stopped', color: 'warning', icon: Ban },
}

export const AGENT_STATE: Readonly<Record<AgentState, Look>> = {
  running: { label: 'Running now', color: 'primary', icon: LoaderCircle },
  queued: { label: 'Waiting to start', color: 'info', icon: Clock },
  idle: { label: 'Ready', color: 'success', icon: CircleCheck },
  paused: { label: 'Paused', color: 'warning', icon: Pause },
}

/** How often an agent may run by itself, in minutes, for the owner to choose from. `null` is only
 * when they start it. */
export const INTERVALS: readonly { title: string; value: number | null }[] = [
  { title: 'Only when I start it', value: null },
  { title: 'Every 15 minutes', value: 15 },
  { title: 'Every 30 minutes', value: 30 },
  { title: 'Every hour', value: 60 },
  { title: 'Every 2 hours', value: 120 },
  { title: 'Every 6 hours', value: 360 },
  { title: 'Every 12 hours', value: 720 },
  { title: 'Every day', value: 1440 },
  { title: 'Every week', value: 10_080 },
]

/** How often an agent runs, in words. */
export function scheduleText(minutes: number | null): string {
  if (minutes === null) return 'Only when you start it'
  const known = INTERVALS.find((choice) => choice.value === minutes)
  if (known) return known.title
  if (minutes % 60 === 0) return `Every ${formatCount(minutes / 60)} hours`
  return `Every ${formatCount(minutes)} minutes`
}

/** How long a run took, or has taken so far, in milliseconds. A run that has not started has
 * taken none. */
export function elapsedMs(run: Pick<Run, 'started_at' | 'finished_at'>, now: number): number {
  if (!run.started_at) return 0
  const end = run.finished_at ? Date.parse(run.finished_at) : now
  return Math.max(0, end - Date.parse(run.started_at))
}

/** What a run came to, in a line for a list: what it found or why it stopped. */
export function outcome(run: Run): string {
  if (run.status === 'failed') return run.error ?? 'It failed.'
  if (run.status === 'cancelled') return 'You stopped it.'
  if (run.status === 'queued') return 'Waiting for the worker to start it.'
  if (run.status === 'running') return 'Working on it now.'
  if (run.findings === 0) return 'Nothing needed your attention.'
  return `${formatCount(run.findings)} ${run.findings === 1 ? 'finding' : 'findings'}`
}

/** The lines a step has to show, if it kept any. */
export function linesOf(step: Pick<Step, 'detail'>): string[] {
  const lines = step.detail.lines
  return Array.isArray(lines)
    ? lines.filter((line): line is string => typeof line === 'string')
    : []
}

/** A severity the model named, as one the page knows: anything else is only information. */
export const severityOf = (value: string): Severity =>
  SEVERITIES.find((known) => known === value) ?? 'info'
