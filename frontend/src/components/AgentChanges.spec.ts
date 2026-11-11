import AgentChanges from '@/components/AgentChanges.vue'
import { finding } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

const since = new Date(Date.now() - 3 * 3_600_000).toISOString()

async function open(
  findings = [finding(), finding({ status: 'ongoing' }), finding({ status: 'ongoing' })],
  gone = [{ severity: 'high', title: 'Telnet is open' }],
) {
  const mounted = await mountWithPlugins(AgentChanges, {
    props: { changes: { since, gone }, findings },
  })
  return {
    ...mounted,
    find: (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`),
  }
}

describe('AgentChanges', () => {
  it('counts what is new, what is still open and what is no longer reported', async () => {
    const { find } = await open()

    expect(find('agent-changes').text()).toContain('Since its run 3 hours ago')
    expect(find('changes-new').text()).toBe('1 new')
    expect(find('changes-open').text()).toBe('2 still open')
    expect(find('changes-gone').text()).toBe('1 no longer reported')
    expect(find('changes-gone-list').text()).toContain('Telnet is open')
  })

  it('has no list of what is gone when nothing is', async () => {
    const { find } = await open([], [])

    expect(find('changes-new').text()).toBe('0 new')
    expect(find('changes-gone').text()).toBe('0 no longer reported')
    expect(find('changes-gone-list').exists()).toBe(false)
  })
})
