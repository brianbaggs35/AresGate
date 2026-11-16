import type {
  Activity,
  Agent,
  AttentionItem,
  Briefing,
  Check,
  AgentDetail,
  AgentSettings,
  Edge,
  Finding,
  Handoff,
  HandoffList,
  Moment,
  Overview,
  PlanStep,
  PlanStepList,
  Performance,
  Proposal,
  ProposalList,
  Run,
  RunDetail,
  Step,
  Template,
  Usage,
  UsageDay,
} from '@/api/agents'
import type { UsageLimit } from '@/api/aiUsage'

/** Agents as the API describes them, for tests of pages that show them. */

export const template = (overrides: Partial<Template> = {}): Template => ({
  key: 'threat_hunter',
  name: 'Threat hunter',
  tagline: 'Reviews the alerts and incidents for anything worth your attention',
  description: 'Reads the incidents that are open and says what, if anything, needs you.',
  icon: 'radar',
  goal: 'Tell me about anything that looks like a real compromise.',
  interval_minutes: 60,
  active: false,
  tools: ['open_incidents'],
  checks: [],
  ready: true,
  setup: ['Connect an integration.', 'Start it once by hand.'],
  proposes: false,
  ...overrides,
})

export const check = (overrides: Partial<Check> = {}): Check => ({
  key: 'intel',
  ok: true,
  text: 'VirusTotal connected, for what is known about addresses',
  fix: 'Add a free VirusTotal key.',
  link: '/integrations/virustotal',
  ...overrides,
})

export const SCANNER = template({
  key: 'exposure_scanner',
  name: 'Exposure scanner',
  tagline: 'Tests your devices for services that should not be open',
  description: 'Connects to a short list of risky ports on the devices AresGate has seen.',
  icon: 'scan-search',
  goal: 'Rank what I should close first.',
  interval_minutes: null,
  active: true,
})

export const usage = (overrides: Partial<Usage> = {}): Usage => ({
  runs: 4,
  calls: 6,
  input_tokens: 9_000,
  output_tokens: 1_200,
  cached_tokens: 3_000,
  cost_micros: 12_500,
  unpriced_calls: 0,
  ...overrides,
})

export const limits = (overrides: Partial<UsageLimit>[] = []): UsageLimit[] => [
  { period: 'day', limit_micros: null, spent_micros: 0, state: 'none', ...overrides[0] },
  { period: 'month', limit_micros: null, spent_micros: 0, state: 'none', ...overrides[1] },
]

export const days = (cost: Record<number, number> = {}): UsageDay[] =>
  Array.from({ length: 30 }, (_, index) => ({
    day: new Date(Date.UTC(2026, 9, 13 + index)).toISOString().slice(0, 10),
    runs: cost[index] ? 1 : 0,
    tokens: cost[index] ? 1_000 : 0,
    cost_micros: cost[index] ?? 0,
  }))

export const settings = (overrides: Partial<AgentSettings> = {}): AgentSettings => ({
  ai_source: 'shared',
  provider: null,
  model: null,
  cleanup_mode: 'suggest',
  asking: {
    provider: 'anthropic',
    label: 'Anthropic',
    model: 'claude-haiku-5-5',
    charges: true,
  },
  reason: null,
  limits: limits(),
  ...overrides,
})

export const performance = (overrides: Partial<Performance> = {}): Performance => ({
  finished: 0,
  succeeded: 0,
  failed: 0,
  cancelled: 0,
  average_seconds: null,
  findings: 0,
  ...overrides,
})

export const run = (overrides: Partial<Run> = {}): Run => ({
  id: 7,
  trigger: 'manual',
  status: 'succeeded',
  requested_at: '2026-11-10T12:00:00Z',
  started_at: '2026-11-10T12:00:02Z',
  finished_at: '2026-11-10T12:00:12Z',
  node: null,
  summary: 'All quiet.',
  findings: 0,
  worst: null,
  by_severity: {},
  rounds: 1,
  error: null,
  ai: '',
  usage: usage({
    runs: 1,
    calls: 1,
    input_tokens: 1_000,
    output_tokens: 200,
    cached_tokens: 0,
    cost_micros: 600,
  }),
  provider: 'anthropic',
  model: 'claude-haiku-5-5',
  ...overrides,
})

export const agent = (overrides: Partial<Agent> = {}): Agent => ({
  id: 3,
  name: 'Night watch',
  template: 'threat_hunter',
  template_name: 'Threat hunter',
  icon: 'radar',
  active: false,
  goal: 'Watch the cameras.',
  enabled: true,
  interval_minutes: 60,
  allow_active: false,
  next_run_at: '2026-11-10T13:00:00Z',
  created_at: '2026-11-09T09:00:00Z',
  state: 'idle',
  last_run: run(),
  recent: ['succeeded', 'failed', 'succeeded'],
  usage: usage(),
  proposals: 0,
  performance: performance({ finished: 3, succeeded: 2, failed: 1, average_seconds: 12 }),
  ...overrides,
})

export const EDGES: Edge[] = [
  { source: 'plan', target: 'act', conditional: false },
  { source: 'act', target: 'think', conditional: false },
  { source: 'think', target: 'act', conditional: true },
  { source: 'think', target: 'report', conditional: true },
]

export const proposal = (overrides: Partial<Proposal> = {}): Proposal => ({
  id: 5,
  agent_id: 3,
  agent_name: 'Night watch',
  kind: 'duplicates',
  title: '3 open incidents say the same thing',
  detail: 'Scan of ssh is open 3 times. Incident 11 stays; the other 2 would be dismissed.',
  action: 'dismiss',
  incident_ids: [12, 13],
  keep_id: 11,
  confidence: 85,
  status: 'pending',
  decided_by: null,
  created_at: '2026-11-10T12:00:00Z',
  decided_at: null,
  ...overrides,
})

export const suggestions = (overrides: Partial<ProposalList> = {}): ProposalList => ({
  pending: [],
  recent: [],
  ...overrides,
})

export const detail = (overrides: Partial<AgentDetail> = {}): AgentDetail => ({
  ...agent(),
  template_info: template(),
  runs: [run()],
  graph: EDGES,
  days: days({ 29: 4_000, 28: 2_500 }),
  suggestions: suggestions(),
  ...overrides,
})

export const overview = (overrides: Partial<Overview> = {}): Overview => ({
  agents: [agent()],
  templates: [template(), SCANNER],
  ai: null,
  usage: usage(),
  limits: limits(),
  proposals: 0,
  attention: [],
  attention_total: 0,
  briefing: null,
  activity: [],
  performance: performance(),
  ...overrides,
})

export const activity = (overrides: Partial<Activity> = {}): Activity => ({
  agent_id: 3,
  agent_name: 'Night watch',
  icon: 'radar',
  run: run(),
  ...overrides,
})

export const attention = (overrides: Partial<AttentionItem> = {}): AttentionItem => ({
  agent_id: 3,
  agent_name: 'Night watch',
  icon: 'radar',
  run_id: 7,
  finished_at: '2026-11-10T12:00:12Z',
  severity: 'high',
  title: 'A scan got further than usual',
  detail: 'Check the firewall rule for port 22.',
  action: 'Close port 22 on the router.',
  status: 'new',
  ...overrides,
})

export const briefing = (overrides: Partial<Briefing> = {}): Briefing => ({
  agent_id: 4,
  agent_name: 'Morning briefing',
  run_id: 9,
  finished_at: '2026-11-10T12:00:12Z',
  summary: 'Nothing needs you today. The firewall was quieter than usual.',
  ...overrides,
})

export const step = (overrides: Partial<Step> = {}): Step => ({
  seq: 1,
  at: '2026-11-10T12:00:03Z',
  node: 'plan',
  title: 'Planned what to look at first: open incidents',
  detail: {},
  ...overrides,
})

export const finding = (overrides: Partial<Finding> = {}): Finding => ({
  severity: 'high',
  title: 'A scan got further than usual',
  detail: 'Check the firewall rule for port 22.',
  cites: [{ kind: 'incident', key: '4', label: 'Incident 4' }],
  status: 'new',
  action: 'Close port 22 on the router.',
  confidence: 'high',
  first_seen_at: '2026-11-10T12:00:12Z',
  runs_seen: 1,
  evidence: [],
  verify: '',
  benign: '',
  ...overrides,
})

export const runDetail = (overrides: Partial<RunDetail> = {}): RunDetail => ({
  ...run(),
  findings_list: [],
  changes: null,
  steps: [
    step(),
    step({
      seq: 2,
      node: 'act',
      title: 'Looked at open incidents',
      detail: { summary: '2 open incidents', lines: ['Incident 4: scan', 'Incident 5: login'] },
    }),
    step({ seq: 3, node: 'think', title: 'Asked Anthropic', detail: {} }),
    step({ seq: 4, node: 'report', title: 'Wrote the report', detail: { findings: 0 } }),
  ],
  call_ids: [],
  ...overrides,
})

/** A hand-off from an agent to another kind of agent, one that was made. */
export const handoff = (overrides: Partial<Handoff> = {}): Handoff => ({
  id: 1,
  run_id: 7,
  from_agent_id: 3,
  from_agent: 'Orchestrator',
  to_kind: 'incident_investigator',
  to_agent_id: 4,
  to_agent: 'Investigator',
  to_run_id: 8,
  subject: 'Incident 12',
  incident_id: 12,
  reason: 'It scanned three devices.',
  status: 'queued',
  refusal: null,
  depth: 1,
  created_at: new Date().toISOString(),
  ...overrides,
})

export const handoffs = (overrides: Partial<HandoffList> = {}): HandoffList => ({
  handoffs: [],
  max_depth: 2,
  per_day: 10,
  made_today: 0,
  ...overrides,
})

/** A step the response planner proposes. */
export const planStep = (overrides: Partial<PlanStep> = {}): PlanStep => ({
  id: 1,
  agent_id: 5,
  agent_name: 'Planner',
  run_id: 9,
  title: 'Move the camera to the guest network',
  detail: 'Put it on the guest VLAN in the router.',
  risk: 'The camera is offline for a minute.',
  incident_id: 12,
  status: 'pending',
  created_at: new Date().toISOString(),
  decided_at: null,
  ...overrides,
})

export const planSteps = (overrides: Partial<PlanStepList> = {}): PlanStepList => ({
  pending: [],
  recent: [],
  ...overrides,
})

/** One moment of an investigation. */
export const moment = (overrides: Partial<Moment> = {}): Moment => ({
  at: '2026-11-16T12:00:00Z',
  agent_id: 3,
  agent: 'Orchestrator',
  run_id: 7,
  kind: 'looked',
  title: 'Looked at open incidents',
  detail: '',
  ...overrides,
})
