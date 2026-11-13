import { describe, expect, it } from 'vitest'

import type { Vulnerability } from '@/api/incidents'
import IncidentVulnerabilities from '@/components/IncidentVulnerabilities.vue'
import { vulnerability } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(...items: Vulnerability[]) {
  const { wrapper } = await mountWithPlugins(IncidentVulnerabilities, {
    props: { vulnerabilities: items.length ? items : [vulnerability()] },
  })
  return wrapper
}

describe('IncidentVulnerabilities', () => {
  it('says how severe a CVE is, that it was exploited, and what it is', async () => {
    const wrapper = await show()
    const card = wrapper.find('[data-test="vulnerability-CVE-2021-44228"]')

    expect(card.find('h3').text()).toBe('CVE-2021-44228')
    expect(card.find('[data-test="vulnerability-score"]').text()).toBe('CVSS 3.1: 10.0, Critical')
    expect(card.find('[data-test="vulnerability-exploited"]').text()).toContain(
      'Exploited in the wild',
    )
    expect(card.find('[data-test="vulnerability-description"]').text()).toContain('Log4j2')
    expect(card.find('[data-test="vulnerability-since"]').text()).toBe('Dec 10, 2021')
    expect(card.find('[data-test="vulnerability-action"]').text()).toBe(
      'Apply updates per vendor instructions. Due Dec 24, 2021.',
    )
    expect(card.find('[data-test="vulnerability-weaknesses"]').text()).toBe('CWE-917')
    expect(card.find('[data-test="vulnerability-vector"]').text()).toContain('CVSS:3.1/AV:N')
    expect(card.text()).toContain('Dec 10, 2021')
    expect(card.find('[data-test="vulnerability-unsettled"]').exists()).toBe(false)
  })

  it('links to the CVE at NVD, safely, and always gives the notice NVD asks for', async () => {
    const wrapper = await show()
    const link = wrapper.find('[data-test="vulnerability-link"]')

    expect(link.attributes('href')).toBe('https://nvd.nist.gov/vuln/detail/CVE-2021-44228')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(link.attributes('target')).toBe('_blank')
    expect(wrapper.find('[data-test="nvd-notice"]').text()).toBe(
      'This product uses data from the NVD API but is not endorsed or certified by the NVD.',
    )
  })

  it.each([
    ['LOW', 'Low'],
    ['MEDIUM', 'Medium'],
    ['HIGH', 'High'],
    ['NONE', 'None'],
  ] as const)('says a %s rating in words', async (severity, word) => {
    const wrapper = await show(vulnerability({ severity, score: 5, exploited: false }))

    expect(wrapper.find('[data-test="vulnerability-score"]').text()).toBe(`CVSS 3.1: 5.0, ${word}`)
    expect(wrapper.find('[data-test="vulnerability-exploited"]').exists()).toBe(false)
  })

  it('says a CVE nobody has asked NVD about is waiting', async () => {
    const wrapper = await show(
      vulnerability({
        state: 'pending',
        score: null,
        severity: null,
        cvss_version: null,
        description: null,
        weaknesses: [],
        vector: null,
        exploited: false,
        exploited_on: null,
        action_due: null,
        required_action: null,
        status: null,
        published_at: null,
      }),
    )

    expect(wrapper.find('[data-test="vulnerability-unsettled"]').text()).toBe(
      'NVD has not been asked about it yet.',
    )
    expect(wrapper.find('[data-test="vulnerability-score"]').exists()).toBe(false)
    expect(wrapper.find('dl').text()).toBe('')
  })

  it('says a CVE NVD has no record of is not known to be severe', async () => {
    const wrapper = await show(
      vulnerability({ state: 'unknown', score: null, severity: null, exploited: false }),
    )

    expect(wrapper.find('[data-test="vulnerability-unsettled"]').text()).toBe(
      'NVD has no record of it yet, so how severe it is is not known.',
    )
  })

  it('says a record with no score yet, with the state NVD gives it or without one', async () => {
    const waiting = await show(
      vulnerability({ score: null, severity: null, status: 'Awaiting Analysis', exploited: false }),
    )
    const bare = await show(
      vulnerability({ score: null, severity: null, status: null, exploited: false }),
    )

    expect(waiting.find('[data-test="vulnerability-unsettled"]').text()).toBe(
      'NVD has not scored it yet (Awaiting Analysis).',
    )
    expect(bare.find('[data-test="vulnerability-unsettled"]').text()).toBe(
      'NVD has not scored it yet.',
    )
  })

  it('marks a rejected CVE', async () => {
    const wrapper = await show(vulnerability({ status: 'Rejected', exploited: false }))

    expect(wrapper.find('[data-test="vulnerability-rejected"]').text()).toBe('Rejected by NVD')
  })

  it('says CISA listed it without a date or an action when it gave none', async () => {
    const wrapper = await show(
      vulnerability({ exploited_on: null, required_action: null, action_due: null }),
    )

    expect(wrapper.find('[data-test="vulnerability-since"]').text()).toBe(
      'a date CISA has not given',
    )
    expect(wrapper.find('[data-test="vulnerability-action"]').exists()).toBe(false)
  })

  it('says what CISA says to do with no due date when it gave none', async () => {
    const wrapper = await show(vulnerability({ action_due: null }))

    expect(wrapper.find('[data-test="vulnerability-action"]').text()).toBe(
      'Apply updates per vendor instructions.',
    )
  })

  it('lists each CVE the incident names', async () => {
    const wrapper = await show(vulnerability(), vulnerability({ id: 'CVE-2019-0708' }))

    expect(wrapper.findAll('h3').map((each) => each.text())).toEqual([
      'CVE-2021-44228',
      'CVE-2019-0708',
    ])
  })
})
