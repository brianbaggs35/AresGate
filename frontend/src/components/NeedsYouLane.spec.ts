import IncidentCard from '@/components/IncidentCard.vue'
import NeedsYouLane from '@/components/NeedsYouLane.vue'
import { incident } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'
import { judged } from '@/test/verdicts'

const three = [
  incident({ id: 3, title: 'Port scan (198.51.100.7)', severity: 'critical' }),
  incident({ id: 2, title: 'Brute force on ssh (203.0.113.9)' }),
  incident({ id: 1, title: 'Beacon (192.0.2.44)', severity: 'medium' }),
]

async function open(props: { incidents?: typeof three; total?: number } = {}) {
  const mounted = await mountWithPlugins(NeedsYouLane, {
    signedIn: 'admin',
    withApp: true,
    props: { incidents: three, total: 3, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, text: (selector: string) => find(selector).text() }
}

describe('NeedsYouLane', () => {
  it('has a card for each incident it is given, in the order it is given them', async () => {
    const { wrapper } = await open()

    expect(
      wrapper.findAllComponents(IncidentCard).map((card) => card.props('incident').id),
    ).toEqual([3, 2, 1])
  })

  it('says what it is for and how many there are', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.find('h2').text()).toBe('Needs you')
    expect(text('needs-you-description')).toContain('3 open incidents')
    expect(wrapper.find('section').attributes('aria-labelledby')).toBe('needs-you-title')
  })

  it('says it in the singular for one', async () => {
    const { text } = await open({ incidents: [three[0]!], total: 1 })

    expect(text('needs-you-description')).toContain('1 open incident,')
  })

  it('leads to every incident when that is all of them', async () => {
    const { find, text } = await open()

    expect(text('needs-you-all')).toBe('Open Incidents')
    expect(find('needs-you-all').attributes('href')).toBe('/incidents')
  })

  it('says how many there are in all when it shows only the first few', async () => {
    const { find, text } = await open({ total: 12 })

    expect(text('needs-you-all')).toBe('See all 12')
    expect(find('needs-you-all').attributes('href')).toBe('/incidents')
  })

  it('passes on what a card was told', async () => {
    const { wrapper } = await open()
    const said = judged()

    wrapper.findComponent(IncidentCard).vm.$emit('judged', said)

    expect(wrapper.findComponent(NeedsYouLane).emitted('judged')).toEqual([[said]])
  })
})
