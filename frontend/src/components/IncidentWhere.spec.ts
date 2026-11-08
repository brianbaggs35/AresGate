import IncidentWhere from '@/components/IncidentWhere.vue'
import { mountWithPlugins } from '@/test/mount'
import { detail, familyBrief } from '@/test/incidents'

async function show(changes = {}) {
  const mounted = await mountWithPlugins(IncidentWhere, { props: { incident: detail(changes) } })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('IncidentWhere', () => {
  it('says the lane, what it means and each fact that put it there', async () => {
    const { find, wrapper } = await show()

    expect(find('lane-chip').text()).toBe('Threat')
    expect(find('where-meaning').text()).toContain('Highly likely')
    expect(find('where-why').text()).toBe("AresGate's rules are 70% sure it is a real attack.")
    expect(wrapper.find('[data-test="stage-trail"]').exists()).toBe(true)
  })

  it('says when it is in none, because it is over or quieted', async () => {
    const { find } = await show({ lane: null })

    expect(find('where-none').text()).toContain('not in a lane')
    expect(find('lane-chip').exists()).toBe(false)
  })

  it('leaves out the facts when there are none', async () => {
    const { find } = await show({ why: [] })

    expect(find('where-why').exists()).toBe(false)
  })

  it('says whose word the call on it is', async () => {
    const { find } = await show({
      call: { classification: 'probe', confidence: 92, basis: 'family' },
    })

    expect(find('where-call').text()).toContain('Probe, 92% sure. The AI judged this kind')
  })

  it('has no call to show when none is made', async () => {
    const { find } = await show()

    expect(find('where-call').exists()).toBe(false)
  })

  it('shows its kind, what is thought of it, and the way to its page', async () => {
    const { find } = await show({
      family: familyBrief({ classification: 'probe', confidence: 90, incidents: 4 }),
    })

    expect(find('where-label').text()).toBe('Brute force on ssh from <address>')
    expect(find('where-family').text()).toContain(
      'From the internet. AI: Probe, 90% sure. 4 incidents of it are going on.',
    )
    expect(find('where-open').attributes('href')).toBe('/threats/kinds/7')
  })

  it('says one incident in the singular', async () => {
    const { find } = await show()

    expect(find('where-family').text()).toContain('1 incident of it is going on.')
  })

  it('has no kind to show when it has none', async () => {
    const { find } = await show({ family: null })

    expect(find('where-family').exists()).toBe(false)
  })
})
