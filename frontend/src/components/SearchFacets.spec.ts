import SearchFacets from '@/components/SearchFacets.vue'
import type { FacetGroup } from '@/search'
import { mountWithPlugins } from '@/test/mount'

const groups = (): FacetGroup[] => [
  {
    name: 'Severity',
    choices: [
      {
        term: 'severity:critical',
        label: 'Critical',
        count: 1,
        on: false,
        color: 'error',
        icon: 'mdi-alert',
      },
      { term: 'severity:high', label: 'High', count: 5, on: true, color: 'error' },
    ],
  },
  {
    name: 'Reported by',
    choices: [
      { term: 'source:wazuh', label: 'Wazuh', count: 7, on: false },
      { term: 'source:crowdsec', label: 'CrowdSec', count: 12345, on: true },
    ],
  },
]

async function open(props: { groups?: FacetGroup[] } = {}) {
  const mounted = await mountWithPlugins(SearchFacets, {
    signedIn: 'admin',
    withApp: true,
    props: { groups: groups(), ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const choices = (group: string) =>
    mounted.wrapper
      .findAll('fieldset')
      .filter((fieldset) => fieldset.find('legend').text() === group)
      .flatMap((fieldset) => fieldset.findAll('button'))
      .map((button) => button.text())
  return { ...mounted, find, choices }
}

describe('SearchFacets', () => {
  it('has a group of buttons for each group it is given, named for a screen reader', async () => {
    const { wrapper, choices } = await open()

    expect(wrapper.findAll('legend').map((legend) => legend.text())).toEqual([
      'Severity',
      'Reported by',
    ])
    expect(choices('Severity')).toEqual(['Critical1', 'High5'])
    expect(choices('Reported by')).toEqual([
      'Wazuh7',
      expect.stringMatching(/^CrowdSec12[,.\s]?345$/),
    ])
  })

  it('has a button for each, with an icon where it has one', async () => {
    const { find } = await open()

    expect(find('facet-severity:critical').find('svg, i').exists()).toBe(true)
    expect(find('facet-source:wazuh').find('svg, i').exists()).toBe(false)
    expect(find('facet-severity:critical').attributes('type')).toBe('button')
  })

  it('says which are on', async () => {
    const { find } = await open()

    expect(find('facet-severity:high').attributes('aria-pressed')).toBe('true')
    expect(find('facet-severity:critical').attributes('aria-pressed')).toBe('false')
    expect(find('facet-source:crowdsec').attributes('aria-pressed')).toBe('true')
    expect(find('facet-source:wazuh').attributes('aria-pressed')).toBe('false')
  })

  it('says which term was chosen', async () => {
    const { find, wrapper } = await open()

    await find('facet-source:wazuh').trigger('click')
    await find('facet-severity:high').trigger('click')

    expect(wrapper.findComponent(SearchFacets).emitted('toggle')).toEqual([
      ['source:wazuh'],
      ['severity:high'],
    ])
  })

  it('has nothing to show when there is nothing to choose', async () => {
    const { find } = await open({ groups: [] })

    expect(find('facets').exists()).toBe(false)
  })
})
