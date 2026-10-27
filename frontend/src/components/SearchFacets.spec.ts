import type { Facets } from '@/api/incidents'
import SearchFacets from '@/components/SearchFacets.vue'
import { mountWithPlugins } from '@/test/mount'

const facets = (changes: Partial<Facets> = {}): Facets => ({
  severity: { info: 0, low: 2, medium: 0, high: 5, critical: 1 },
  sources: [
    { key: 'wazuh', name: 'Wazuh', count: 7 },
    { key: 'crowdsec', name: 'CrowdSec', count: 1 },
  ],
  ...changes,
})

async function open(props: { facets?: Facets; search?: string } = {}) {
  const mounted = await mountWithPlugins(SearchFacets, {
    signedIn: 'admin',
    withApp: true,
    props: { facets: facets(), search: '', ...props },
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
  it('counts the severities that have any, the most serious first', async () => {
    const { choices } = await open()

    expect(choices('Severity')).toEqual(['Critical1', 'High5', 'Low2'])
  })

  it('counts what each integration reported, in the order it is given', async () => {
    const { choices } = await open()

    expect(choices('Reported by')).toEqual(['Wazuh7', 'CrowdSec1'])
  })

  it('shows a count with a thousands separator', async () => {
    const { choices } = await open({
      facets: facets({ sources: [{ key: 'wazuh', name: 'Wazuh', count: 12345 }] }),
    })

    expect(choices('Reported by')).toEqual([expect.stringMatching(/^Wazuh12[,.\s]?345$/)])
  })

  it('has a button for each, with an icon for the severities', async () => {
    const { find } = await open()

    expect(find('facet-severity:critical').find('svg').exists()).toBe(true)
    expect(find('facet-source:wazuh').find('svg').exists()).toBe(false)
    expect(find('facet-severity:critical').attributes('type')).toBe('button')
  })

  it('says which are on, by the search that is applied', async () => {
    const { find } = await open({ search: 'ssh severity:high source:crowdsec' })

    expect(find('facet-severity:high').attributes('aria-pressed')).toBe('true')
    expect(find('facet-severity:critical').attributes('aria-pressed')).toBe('false')
    expect(find('facet-source:crowdsec').attributes('aria-pressed')).toBe('true')
    expect(find('facet-source:wazuh').attributes('aria-pressed')).toBe('false')
  })

  it('still offers a severity that is on when nothing is left at it', async () => {
    const { choices } = await open({
      facets: facets({ severity: { info: 0, low: 0, medium: 0, high: 0, critical: 0 } }),
      search: 'severity:medium',
    })

    expect(choices('Severity')).toEqual(['Medium0'])
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
    const { find } = await open({
      facets: {
        severity: { info: 0, low: 0, medium: 0, high: 0, critical: 0 },
        sources: [],
      },
    })

    expect(find('facets').exists()).toBe(false)
  })
})
