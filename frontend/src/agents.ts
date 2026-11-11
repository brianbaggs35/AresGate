import {
  Activity,
  Ban,
  Bot,
  Brain,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleHelp,
  Clock,
  Eye,
  FileText,
  Flame,
  HeartPulse,
  ListChecks,
  LoaderCircle,
  Microscope,
  Newspaper,
  Pause,
  Radar,
  ScanSearch,
  ShieldAlert,
  Sparkles,
  Swords,
  Telescope,
  Wifi,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type {
  Agent,
  AgentState,
  Finding,
  Edge,
  ProposalStatus,
  Run,
  RunStatus,
  Step,
  Usage,
  UsageDay,
} from '@/api/agents'
import type { BarSeries } from '@/charts/BarChart.vue'
import { dayLabel, formatMoney, formatTokens } from '@/aiUsage'
import type { ChatCite } from '@/api/aiChat'
import { severityColor } from '@/charts/palette'
import { formatAgo, formatCount } from '@/format'
import { SEVERITIES, SEVERITY, type Severity } from '@/severity'

type Icon = NonNullable<IconProps['icon']>

/** The icon of each kind of agent, by the name the API gives it. */
const ICONS: Readonly<Record<string, Icon>> = {
  radar: Radar,
  telescope: Telescope,
  'heart-pulse': HeartPulse,
  'scan-search': ScanSearch,
  sparkles: Sparkles,
  'shield-alert': ShieldAlert,
  wifi: Wifi,
  flame: Flame,
  swords: Swords,
  newspaper: Newspaper,
  activity: Activity,
  microscope: Microscope,
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

/** All the tokens of what agents asked of the AI, what was sent and what came back. */
export const tokensOf = (usage: Pick<Usage, 'input_tokens' | 'output_tokens'>): number =>
  usage.input_tokens + usage.output_tokens

/** How much of what was sent the provider already had cached, as a percentage: what a cache saves
 * is the point of asking in the same words each time. */
export function cachedShare(usage: Pick<Usage, 'input_tokens' | 'cached_tokens'>): number {
  return usage.input_tokens === 0 ? 0 : Math.round((usage.cached_tokens / usage.input_tokens) * 100)
}

/** What it cost, or that nothing was asked: a request to a model with no known price is not
 * counted in it, and the words say so. */
export function costWords(usage: Pick<Usage, 'calls' | 'cost_micros' | 'unpriced_calls'>): string {
  if (usage.calls === 0) return 'No AI used'
  if (usage.unpriced_calls === 0) return formatMoney(usage.cost_micros)
  return usage.cost_micros === 0 ? 'Price unknown' : `${formatMoney(usage.cost_micros)} and more`
}

/** What a run or an agent used of the AI in a line: requests, tokens and cost. */
export function usageLine(usage: Usage): string {
  if (usage.calls === 0) return 'Used no AI'
  const requests = `${formatCount(usage.calls)} ${usage.calls === 1 ? 'request' : 'requests'}`
  return `${requests} · ${formatTokens(tokensOf(usage))} tokens · ${costWords(usage)}`
}

/** Each day's cost as a bar chart reads it: the labels, and the cost in dollars of each. */
export function dailyCost(days: readonly UsageDay[]): {
  categories: string[]
  series: BarSeries[]
} {
  return {
    categories: days.map((day) => dayLabel(`${day.day}T12:00:00Z`)),
    series: [{ id: 'cost', label: 'Cost', values: days.map((day) => day.cost_micros / 1_000_000) }],
  }
}

/** What applying a suggestion does to the incidents it is about, in the words of a button's hint. */
export const PROPOSAL_ACTION: Readonly<Record<string, string>> = {
  dismiss: 'It would dismiss',
  resolve: 'It would mark resolved',
  not_suspicious: 'It would mark not suspicious',
}

/** Where a suggestion is, in words and a color: never a color alone. */
export const PROPOSAL_STATUS: Readonly<Record<ProposalStatus, { label: string; color: string }>> = {
  pending: { label: 'Waiting', color: 'info' },
  applied: { label: 'Done', color: 'success' },
  dismissed: { label: 'Left alone', color: 'default' },
  undone: { label: 'Taken back', color: 'warning' },
}

export const incidentsWords = (count: number): string =>
  `${formatCount(count)} ${count === 1 ? 'incident' : 'incidents'}`

const agentsWords = (count: number): string =>
  `${formatCount(count)} ${count === 1 ? 'agent' : 'agents'}`

/** How the agents are doing together, in a line for the top of the page: what needs the owner, and
 * if nothing does, whether any is at work. */
export function fleetLine(
  agents: readonly Pick<Agent, 'state'>[],
  attention: number,
): { text: string; tone: 'bad' | 'working' | 'good' | 'idle' } {
  const working = agents.filter((agent) => agent.state === 'running' || agent.state === 'queued')
  const busy = working.length ? `${agentsWords(working.length)} at work` : ''
  if (attention > 0) {
    const needs = `${formatCount(attention)} ${attention === 1 ? 'thing needs' : 'things need'} you`
    return { text: busy ? `${needs} · ${busy}` : needs, tone: 'bad' }
  }
  if (busy) return { text: busy, tone: 'working' }
  if (agents.length) return { text: 'All quiet: nothing needs you', tone: 'good' }
  return { text: 'No agents yet', tone: 'idle' }
}

/** How sure an agent says it is, in words: never a color alone. */
export const CONFIDENCE: Readonly<Record<Finding['confidence'], { label: string; icon: Icon }>> = {
  low: { label: 'Not very sure', icon: CircleHelp },
  medium: { label: 'Fairly sure', icon: CircleDot },
  high: { label: 'Sure', icon: CircleCheck },
}

/** How long a finding has been reported, in a line. */
export function reportedFor(finding: Pick<Finding, 'runs_seen' | 'first_seen_at'>): string {
  return finding.runs_seen > 1
    ? `Reported in ${formatCount(finding.runs_seen)} runs in a row, since ${formatAgo(finding.first_seen_at)}`
    : 'First time it was reported'
}

/** The findings of an agent's recent runs, by how serious, for the chart that shows whether it is
 * finding more or less: a bar for each finished run, oldest first, a series for each severity
 * there were any of, least serious first so the worst sit on top. */
export function findingsOverTime(runs: readonly Run[]): {
  categories: string[]
  series: BarSeries[]
} {
  const done = runs
    .filter((run) => run.status === 'succeeded')
    .slice(0, MAX_BARS)
    .reverse()
  return {
    categories: done.map((run) => `Run ${run.id}`),
    series: SEVERITIES.flatMap((severity) =>
      done.some((run) => run.by_severity[severity])
        ? [
            {
              id: severity,
              label: SEVERITY[severity].label,
              values: done.map((run) => run.by_severity[severity] ?? 0),
              color: severityColor(severity),
              icon: SEVERITY[severity].icon,
            },
          ]
        : [],
    ),
  }
}

/** How many runs the chart of findings over time draws. */
export const MAX_BARS = 14

/** How long a step took: until the next one began, or null for the last, which has no next. */
export function tookMs(step: Pick<Step, 'at'>, next: Pick<Step, 'at'> | undefined): number | null {
  return next ? Math.max(0, Date.parse(next.at) - Date.parse(step.at)) : null
}

/** What a step looked at that has a page of its own, such as an incident. */
export function refsOf(step: Pick<Step, 'detail'>): ChatCite[] {
  const refs = step.detail.refs
  if (!Array.isArray(refs)) return []
  return refs.filter(
    (ref): ref is ChatCite =>
      typeof ref === 'object' &&
      ref !== null &&
      typeof (ref as ChatCite).kind === 'string' &&
      typeof (ref as ChatCite).key === 'string' &&
      typeof (ref as ChatCite).label === 'string',
  )
}

/** How many lines a step saw that it did not keep. */
export const moreOf = (step: Pick<Step, 'detail'>): number =>
  typeof step.detail.more === 'number' ? step.detail.more : 0
