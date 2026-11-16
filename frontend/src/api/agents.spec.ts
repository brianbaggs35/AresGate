import {
  applyProposal,
  approveStep,
  cancelRun,
  changeAgent,
  createAgent,
  dismissProposal,
  dismissStep,
  fetchAgent,
  fetchAgentSettings,
  fetchAgents,
  fetchHandoffs,
  fetchIncidentTimeline,
  fetchPlanSteps,
  fetchProposals,
  fetchRun,
  fetchRunTimeline,
  removeAgent,
  saveAgentSettings,
  startRun,
  undoProposal,
  type AgentChoices,
} from '@/api/agents'
import * as client from '@/api/client'

const CHOICES: AgentChoices = {
  name: 'Night watch',
  goal: 'Watch the cameras.',
  interval_minutes: 60,
  enabled: true,
  allow_active: false,
}

describe('agents', () => {
  it('lists them with what one can be made from', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ agents: [] })

    await expect(fetchAgents()).resolves.toEqual({ agents: [] })
    expect(get).toHaveBeenCalledWith('/agents')
  })

  it('reads one', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 3 })

    await fetchAgent(3)

    expect(get).toHaveBeenCalledWith('/agents/3')
  })

  it('makes one from a kind, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 3 })

    await expect(createAgent('threat_hunter', CHOICES, 'a-token')).resolves.toEqual({ id: 3 })
    expect(post).toHaveBeenCalledWith(
      '/agents',
      { template: 'threat_hunter', ...CHOICES },
      'a-token',
    )
  })

  it('changes one, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ id: 3 })

    await changeAgent(3, CHOICES, 'a-token')

    expect(put).toHaveBeenCalledWith('/agents/3', CHOICES, 'a-token')
  })

  it('removes one, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeAgent(3, 'a-token')

    expect(remove).toHaveBeenCalledWith('/agents/3', 'a-token')
  })

  it('asks for a run, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 9 })

    await startRun(3, 'a-token')

    expect(post).toHaveBeenCalledWith('/agents/3/runs', undefined, 'a-token')
  })

  it('reads a run with its steps', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 9 })

    await fetchRun(3, 9)

    expect(get).toHaveBeenCalledWith('/agents/3/runs/9')
  })

  it('stops a run, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 9 })

    await cancelRun(3, 9, 'a-token')

    expect(post).toHaveBeenCalledWith('/agents/3/runs/9/cancel', undefined, 'a-token')
  })

  it('reads which AI the agents ask', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ ai_source: 'shared' })

    await expect(fetchAgentSettings()).resolves.toEqual({ ai_source: 'shared' })
    expect(get).toHaveBeenCalledWith('/agents/settings')
  })

  it('keeps which AI the agents ask and what they may spend, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ ai_source: 'off' })
    const choices = { ai_source: 'off', provider: null, model: null, daily: '1', monthly: null }

    await saveAgentSettings(choices as never, 'a-token')

    expect(put).toHaveBeenCalledWith('/agents/settings', choices, 'a-token')
  })

  it('reads, applies, turns down and takes back suggestions', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ pending: [], recent: [] })
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({})

    await fetchProposals()
    await applyProposal(5, 'token')
    await dismissProposal(5, 'token')
    await undoProposal(5, 'token')

    expect(get).toHaveBeenCalledWith('/agents/proposals')
    expect(post).toHaveBeenCalledWith('/agents/proposals/5/apply', undefined, 'token')
    expect(post).toHaveBeenCalledWith('/agents/proposals/5/dismiss', undefined, 'token')
    expect(post).toHaveBeenCalledWith('/agents/proposals/5/undo', undefined, 'token')
  })

  it('asks for hand-offs, the planner steps and the timelines, and decides on a step', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({})

    await fetchHandoffs()
    await fetchPlanSteps()
    await fetchPlanSteps(12)
    await fetchRunTimeline(3, 7)
    await fetchIncidentTimeline(12)
    await approveStep(5, 'token')
    await dismissStep(6, 'token')

    expect(get).toHaveBeenCalledWith('/agents/handoffs')
    expect(get).toHaveBeenCalledWith('/agents/plan-steps')
    expect(get).toHaveBeenCalledWith('/agents/plan-steps?incident_id=12')
    expect(get).toHaveBeenCalledWith('/agents/3/runs/7/timeline')
    expect(get).toHaveBeenCalledWith('/agents/timeline?incident_id=12')
    expect(post).toHaveBeenCalledWith('/agents/plan-steps/5/approve', undefined, 'token')
    expect(post).toHaveBeenCalledWith('/agents/plan-steps/6/dismiss', undefined, 'token')
  })
})
