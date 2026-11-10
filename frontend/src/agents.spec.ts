import { Bot, Radar, Telescope } from '@lucide/vue'

import {
  AGENT_STATE,
  INTERVALS,
  MAX_ROUNDS,
  NODES,
  RUN_STATUS,
  agentIcon,
  anyLive,
  elapsedMs,
  isLive,
  linesOf,
  nodeInfo,
  nodeState,
  outcome,
  scheduleText,
  severityOf,
  shape,
} from '@/agents'
import { EDGES, agent, run, step } from '@/test/agents'

describe('agent icons', () => {
  it('gives each kind its own, and a robot to one it does not know', () => {
    expect(agentIcon('radar')).toBe(Radar)
    expect(agentIcon('telescope')).toBe(Telescope)
    expect(agentIcon('something-new')).toBe(Bot)
  })
})

describe('the steps of a run', () => {
  it('names each of them and says what it does', () => {
    expect(NODES.map((node) => node.id)).toEqual(['plan', 'act', 'think', 'report'])
    expect(nodeInfo('think').label).toBe('Think')
  })

  it('shows a step it does not know by its own name', () => {
    expect(nodeInfo('mystery')).toMatchObject({ id: 'mystery', label: 'mystery', hint: '' })
  })

  it('takes the nodes of the graph in the order they run, and the arrows that go back as the loop', () => {
    const { nodes, loops } = shape(EDGES)

    expect(nodes.map((node) => node.id)).toEqual(['plan', 'act', 'think', 'report'])
    expect(loops).toEqual([{ source: 'think', target: 'act', conditional: true }])
  })

  it('draws only the nodes the graph has', () => {
    const { nodes, loops } = shape([{ source: 'plan', target: 'report', conditional: false }])

    expect(nodes.map((node) => node.id)).toEqual(['plan', 'report'])
    expect(loops).toEqual([])
  })

  it('says the maximum number of rounds the backend allows', () => {
    expect(MAX_ROUNDS).toBe(3)
  })
})

describe('where a step is in a run', () => {
  const steps = [step({ node: 'plan' }), step({ node: 'act' })]

  it('is waiting where there is no run', () => {
    expect(nodeState('plan', null, [])).toBe('waiting')
  })

  it('is going for the step a running run is in', () => {
    expect(nodeState('act', run({ status: 'running', node: 'act' }), steps)).toBe('active')
  })

  it('is done for a step that said what it did, and waiting for one not reached yet', () => {
    const going = run({ status: 'running', node: 'act' })

    expect(nodeState('plan', going, steps)).toBe('done')
    expect(nodeState('report', going, steps)).toBe('waiting')
    expect(nodeState('plan', run({ status: 'queued' }), [])).toBe('waiting')
  })

  it('is not reached for a step a finished run never got to', () => {
    expect(nodeState('report', run({ status: 'failed' }), steps)).toBe('skipped')
    expect(nodeState('plan', run({ status: 'cancelled' }), steps)).toBe('done')
  })
})

describe('what is live', () => {
  it('is a run that is waiting or going', () => {
    expect(isLive(run({ status: 'queued' }))).toBe(true)
    expect(isLive(run({ status: 'running' }))).toBe(true)
    expect(isLive(run({ status: 'succeeded' }))).toBe(false)
    expect(isLive(null)).toBe(false)
    expect(isLive(undefined)).toBe(false)
  })

  it('is an agent that is waiting or going', () => {
    expect(anyLive([agent({ state: 'idle' }), agent({ state: 'queued' })])).toBe(true)
    expect(anyLive([agent({ state: 'running' })])).toBe(true)
    expect(anyLive([agent({ state: 'paused' }), agent({ state: 'idle' })])).toBe(false)
    expect(anyLive([])).toBe(false)
  })

  it('has a look and a name for each status and state', () => {
    expect(Object.keys(RUN_STATUS)).toHaveLength(5)
    expect(Object.keys(AGENT_STATE)).toHaveLength(4)
  })
})

describe('schedules', () => {
  it('says only when you start it for none', () => {
    expect(scheduleText(null)).toBe('Only when you start it')
  })

  it('uses the words of the choices there are', () => {
    expect(scheduleText(60)).toBe('Every hour')
    expect(INTERVALS[0]?.value).toBeNull()
  })

  it('says any other interval in hours when it is whole hours, and otherwise in minutes', () => {
    expect(scheduleText(180)).toBe('Every 3 hours')
    expect(scheduleText(45)).toBe('Every 45 minutes')
  })
})

describe('how long a run took', () => {
  const finished = { started_at: '2026-11-10T12:00:00Z', finished_at: '2026-11-10T12:00:10Z' }

  it('is none for a run that has not started', () => {
    expect(elapsedMs({ started_at: null, finished_at: null }, 0)).toBe(0)
  })

  it('is from its start to its end', () => {
    expect(elapsedMs(finished, 0)).toBe(10_000)
  })

  it('is from its start until now while it goes, and never below none', () => {
    const going = { started_at: '2026-11-10T12:00:00Z', finished_at: null }

    expect(elapsedMs(going, Date.parse('2026-11-10T12:00:04Z'))).toBe(4000)
    expect(elapsedMs(going, Date.parse('2026-11-10T11:00:00Z'))).toBe(0)
  })
})

describe('what a run came to', () => {
  it('says why one failed, or that it did without saying why', () => {
    expect(outcome(run({ status: 'failed', error: 'It broke.' }))).toBe('It broke.')
    expect(outcome(run({ status: 'failed', error: null }))).toBe('It failed.')
  })

  it('says what the owner did and what it waits for', () => {
    expect(outcome(run({ status: 'cancelled' }))).toBe('You stopped it.')
    expect(outcome(run({ status: 'queued' }))).toBe('Waiting for the worker to start it.')
    expect(outcome(run({ status: 'running' }))).toBe('Working on it now.')
  })

  it('counts what a finished run found', () => {
    expect(outcome(run({ findings: 0 }))).toBe('Nothing needed your attention.')
    expect(outcome(run({ findings: 1 }))).toBe('1 finding')
    expect(outcome(run({ findings: 1200 }))).toBe('1,200 findings')
  })
})

describe('what a step kept', () => {
  it('has its lines, as words only', () => {
    expect(linesOf({ detail: { lines: ['a', 4, 'b'] } })).toEqual(['a', 'b'])
  })

  it('has none when it kept none', () => {
    expect(linesOf({ detail: {} })).toEqual([])
    expect(linesOf({ detail: { lines: 'not a list' } })).toEqual([])
  })
})

describe('severities', () => {
  it('are the ones the page knows, and information for any other', () => {
    expect(severityOf('critical')).toBe('critical')
    expect(severityOf('mysterious')).toBe('info')
  })
})
