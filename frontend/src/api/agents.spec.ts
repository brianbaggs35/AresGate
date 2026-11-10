import {
  cancelRun,
  changeAgent,
  createAgent,
  fetchAgent,
  fetchAgents,
  fetchRun,
  removeAgent,
  startRun,
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
})
