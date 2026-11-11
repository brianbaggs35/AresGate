import * as agentsApi from '@/api/agents'
import { ApiError } from '@/api/client'
import AgentProposals from '@/components/AgentProposals.vue'
import { proposal, suggestions } from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'

async function open(list = suggestions({ pending: [proposal()] })) {
  const apply = vi.spyOn(agentsApi, 'applyProposal').mockResolvedValue(proposal())
  const dismiss = vi.spyOn(agentsApi, 'dismissProposal').mockResolvedValue(proposal())
  const undo = vi.spyOn(agentsApi, 'undoProposal').mockResolvedValue(proposal())
  const mounted = await mountWithPlugins(AgentProposals, {
    props: { suggestions: list },
    signedIn: 'admin',
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, find, click, apply, dismiss, undo }
}

describe('AgentProposals', () => {
  it('says there is nothing to tidy when there is nothing', async () => {
    const { find } = await open(suggestions())

    expect(find('proposals-none').text()).toContain('Nothing to tidy yet')
    expect(find('proposals-pending').exists()).toBe(false)
  })

  it('says what it would do, how sure it is and to which incidents', async () => {
    const { find, wrapper } = await open()

    expect(find('proposal-title').text()).toBe('3 open incidents say the same thing')
    expect(find('proposal-sure').text()).toBe('85% sure')
    expect(find('proposal-detail').text()).toContain('Incident 11 stays')
    expect(find('proposal-does').text()).toContain('It would dismiss 2 incidents: 12, 13')
    expect(
      wrapper.findAll('[data-test="proposal-incident"]').map((link) => link.attributes('href')),
    ).toEqual(['/incidents/12', '/incidents/13'])
    expect(find('proposal-keep').attributes('href')).toBe('/incidents/11')
  })

  it('shows the first few incidents and counts the rest, and says nothing stays when none does', async () => {
    const { find, wrapper } = await open(
      suggestions({
        pending: [
          proposal({
            action: 'resolve',
            keep_id: null,
            incident_ids: [1, 2, 3, 4, 5, 6, 7, 8],
          }),
        ],
      }),
    )

    expect(wrapper.findAll('[data-test="proposal-incident"]')).toHaveLength(6)
    expect(find('proposal-does').text()).toContain('It would mark resolved 8 incidents')
    expect(find('proposal-does').text()).toContain('and 2 more')
    expect(find('proposal-keep').exists()).toBe(false)
  })

  it('speaks of one incident in the singular and of an action it does not know by its name', async () => {
    const { find } = await open(
      suggestions({
        pending: [proposal({ action: 'merge', incident_ids: [9], keep_id: null })],
      }),
    )

    expect(find('proposal-does').text()).toContain('merge 1 incident: 9')
  })

  it('applies one and tells whoever shows it', async () => {
    const { find, click, apply, wrapper } = await open()

    await click('proposal-apply')

    expect(apply).toHaveBeenCalledWith(5, TOKEN)
    expect(wrapper.emitted().changed).toEqual([['Done: 3 open incidents say the same thing.']])
    expect(find('proposal-problem').exists()).toBe(false)
  })

  it('turns one down', async () => {
    const { click, dismiss, wrapper } = await open()

    await click('proposal-dismiss')

    expect(dismiss).toHaveBeenCalledWith(5, TOKEN)
    expect(wrapper.emitted().changed).toEqual([['Left as it is.']])
  })

  it('says why a change was refused, and clears it with the next', async () => {
    const { find, click, apply, wrapper } = await open()
    apply.mockRejectedValueOnce(new ApiError(409, 'This suggestion has already been applied.'))

    await click('proposal-apply')

    expect(find('proposal-problem').text()).toBe('This suggestion has already been applied.')
    expect(wrapper.emitted().changed).toBeUndefined()

    await click('proposal-apply')

    expect(find('proposal-problem').exists()).toBe(false)
  })

  it('lists what was decided, and takes back what was applied', async () => {
    const { wrapper, find, click, undo } = await open(
      suggestions({
        recent: [
          proposal({
            id: 8,
            status: 'applied',
            decided_by: 'agent',
            decided_at: '2026-11-10T12:00:00Z',
          }),
          proposal({ id: 9, status: 'dismissed', decided_by: 'owner', decided_at: null }),
          proposal({ id: 10, status: 'undone', decided_by: 'owner', decided_at: null }),
        ],
      }),
    )

    expect(wrapper.findAll('[data-test="recent-status"]').map((chip) => chip.text())).toEqual([
      'Done',
      'Left alone',
      'Taken back',
    ])
    expect(wrapper.findAll('[data-test="recent-when"]')[0]!.text()).toContain('by the agent')
    expect(wrapper.findAll('[data-test="proposal-undo"]')).toHaveLength(1)

    await click('proposal-undo')

    expect(undo).toHaveBeenCalledWith(8, TOKEN)
    expect(wrapper.emitted().changed).toEqual([['Taken back.']])
    expect(find('proposals-none').exists()).toBe(false)
  })
})
