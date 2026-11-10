import type {
  Agent,
  AgentDetail,
  Edge,
  Finding,
  Overview,
  Run,
  RunDetail,
  Step,
  Template,
} from '@/api/agents'

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
  rounds: 1,
  error: null,
  ai: '',
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
  ...overrides,
})

export const EDGES: Edge[] = [
  { source: 'plan', target: 'act', conditional: false },
  { source: 'act', target: 'think', conditional: false },
  { source: 'think', target: 'act', conditional: true },
  { source: 'think', target: 'report', conditional: true },
]

export const detail = (overrides: Partial<AgentDetail> = {}): AgentDetail => ({
  ...agent(),
  template_info: template(),
  runs: [run()],
  graph: EDGES,
  ...overrides,
})

export const overview = (overrides: Partial<Overview> = {}): Overview => ({
  agents: [agent()],
  templates: [template(), SCANNER],
  ai: null,
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
  ...overrides,
})

export const runDetail = (overrides: Partial<RunDetail> = {}): RunDetail => ({
  ...run(),
  findings_list: [],
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
