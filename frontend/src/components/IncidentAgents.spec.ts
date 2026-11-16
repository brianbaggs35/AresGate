import * as agentsApi from '@/api/agents'
import { ApiError } from '@/api/client'
import IncidentAgents from '@/components/IncidentAgents.vue'
import { moment, planStep, planSteps } from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open({
  moments = [moment({ kind: 'concluded', title: 'high: Brute force' })],
  steps = planSteps({ pending: [planStep()] }),
  fails = false,
}: { moments?: agentsApi.Moment[]; steps?: agentsApi.PlanStepList; fails?: boolean } = {}) {
  const told = vi.spyOn(agentsApi, 'fetchIncidentTimeline')
  const planned = vi.spyOn(agentsApi, 'fetchPlanSteps')
  if (fails) told.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
  else told.mockResolvedValue(moments)
  planned.mockResolvedValue(steps)
  const mounted = await mountWithPlugins(IncidentAgents, {
    props: { incidentId: 12 },
    signedIn: 'admin',
    withApp: true,
  })
  await flushPromises()
  return {
    ...mounted,
    told,
    planned,
    find: (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`),
  }
}

describe('IncidentAgents', () => {
  it('shows what the agents concluded and the steps waiting for the owner', async () => {
    const { find, told, planned } = await open()

    expect(told).toHaveBeenCalledWith(12)
    expect(planned).toHaveBeenCalledWith(12)
    expect(find('agents-card').text()).toContain('high: Brute force')
    expect(find('step').text()).toContain('Move the camera')
  })

  it('shows only the timeline when no step was proposed', async () => {
    const { find } = await open({ steps: planSteps() })

    expect(find('investigation').exists()).toBe(true)
    expect(find('steps-root').exists()).toBe(false)
  })

  it('shows nothing for an incident no agent has looked at', async () => {
    const { find } = await open({ moments: [], steps: planSteps() })

    expect(find('agents-card').exists()).toBe(false)
  })

  it('shows nothing when it could not ask', async () => {
    const { find } = await open({ fails: true })

    expect(find('agents-card').exists()).toBe(false)
  })

  it('asks again when a step is decided', async () => {
    vi.spyOn(agentsApi, 'approveStep').mockResolvedValue(planStep({ status: 'approved' }))
    const { find, told, planned } = await open()
    planned.mockResolvedValue(
      planSteps({
        recent: [planStep({ status: 'approved', decided_at: new Date().toISOString() })],
      }),
    )

    await find('step-approve').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(told).toHaveBeenCalledTimes(2)
    expect(find('steps-pending').exists()).toBe(false)
  })
})
