import * as agentsApi from '@/api/agents'
import { ApiError } from '@/api/client'
import AgentSteps from '@/components/AgentSteps.vue'
import { planStep, planSteps } from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'

async function open(list = planSteps({ pending: [planStep()] })) {
  const approve = vi.spyOn(agentsApi, 'approveStep').mockResolvedValue(planStep())
  const dismiss = vi.spyOn(agentsApi, 'dismissStep').mockResolvedValue(planStep())
  const mounted = await mountWithPlugins(AgentSteps, { props: { steps: list }, signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, find, click, approve, dismiss }
}

describe('AgentSteps', () => {
  it('says there are no steps when there are none', async () => {
    const { find } = await open(planSteps())

    expect(find('steps-none').text()).toContain('No steps yet')
    expect(find('steps-pending').exists()).toBe(false)
  })

  it('says what to do, what it risks and which incident it is about', async () => {
    const { find } = await open()

    expect(find('step-title').text()).toBe('Move the camera to the guest network')
    expect(find('step-detail').text()).toContain('guest VLAN')
    expect(find('step-risk').text()).toBe('What it risks: The camera is offline for a minute.')
    expect(find('step-incident').attributes('href')).toBe('/incidents/12')
  })

  it('leaves out what a step does not say', async () => {
    const { find } = await open(
      planSteps({ pending: [planStep({ detail: '', risk: '', incident_id: null })] }),
    )

    expect(find('step-detail').exists()).toBe(false)
    expect(find('step-risk').exists()).toBe(false)
    expect(find('step-incident').exists()).toBe(false)
  })

  it('approves a step and tells whoever shows it', async () => {
    const { click, approve, wrapper } = await open()

    await click('step-approve')

    expect(approve).toHaveBeenCalledWith(1, TOKEN)
    expect(wrapper.emitted('changed')).toEqual([
      ['Approved. It is on the incident as a task for you.'],
    ])
  })

  it('dismisses a step', async () => {
    const { click, dismiss, wrapper } = await open()

    await click('step-dismiss')

    expect(dismiss).toHaveBeenCalledWith(1, TOKEN)
    expect(wrapper.emitted('changed')).toEqual([['Dismissed.']])
  })

  it('says why a step could not be decided, and tells no one', async () => {
    const { find, click, approve, wrapper } = await open()
    approve.mockRejectedValue(new ApiError(409, 'This step has already been approved.', 'x'))

    await click('step-approve')

    expect(find('step-problem').text()).toContain('already been approved')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('lists what was decided lately with its words', async () => {
    const { wrapper } = await open(
      planSteps({
        recent: [
          planStep({
            id: 2,
            title: 'Done one',
            status: 'approved',
            decided_at: new Date().toISOString(),
          }),
          planStep({ id: 3, title: 'Left one', status: 'dismissed', decided_at: null }),
        ],
      }),
    )

    expect(wrapper.findAll('[data-test="recent-status"]').map((chip) => chip.text())).toEqual([
      'Approved',
      'Dismissed',
    ])
    expect(wrapper.findAll('[data-test="recent-title"]').map((item) => item.text())).toEqual([
      'Done one',
      'Left one',
    ])
    expect(wrapper.findAll('[data-test="recent-when"]')).toHaveLength(1)
  })
})
