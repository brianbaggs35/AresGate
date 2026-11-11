import ChainPath from '@/components/ChainPath.vue'
import { mountWithPlugins } from '@/test/mount'
import { chainDetail, chainStep } from '@/test/threats'
import type { ChainDetail } from '@/api/threats'

async function open(changes: Partial<ChainDetail> = {}) {
  return mountWithPlugins(ChainPath, { props: { chain: chainDetail(changes) } })
}

describe('ChainPath', () => {
  it('draws the steps in order with the device between the one that got in and the one that called out', async () => {
    const { wrapper } = await open()

    const items = wrapper.findAll('[data-test="chain-path"] > li')
    expect(items.map((item) => item.attributes('data-test'))).toEqual([
      'path-step',
      'path-device',
      'path-step',
    ])
    expect(wrapper.findAll('[data-test="step-role"]').map((each) => each.text())).toEqual([
      'Got in from the internet',
      'Then the device called out',
    ])
    expect(wrapper.find('[data-test="path-device"]').text()).toContain('Kitchen camera')
  })

  it('says each step was seen or is only inferred, and draws the two apart', async () => {
    const { wrapper } = await open({
      confirmed: false,
      path: [chainStep(), chainStep({ role: 'callout', link: 'inferred', incident_id: 12 })],
    })

    const steps = wrapper.findAll('[data-test="path-step"]')
    expect(steps.map((step) => step.attributes('data-link'))).toEqual(['confirmed', 'inferred'])
    expect(wrapper.findAll('[data-test="step-link"]').map((each) => each.text())).toEqual([
      'Seen',
      'Inferred',
    ])
    expect(wrapper.find('[data-test="path-device"]').text()).toContain('a guess')
  })

  it('says why each step is in the chain and which programs saw it', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="step-reason"]').text()).toContain('CVE-2021-44228')
    expect(wrapper.find('[data-test="step-sources"]').text()).toContain(
      'Reported by Suricata, Wazuh.',
    )
  })

  it('counts an alert that two programs reported once, and says who saw it', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="step-duplicates"]').text()).toContain(
      '1 alert was also reported by another program, counted once.',
    )
    expect(wrapper.find('[data-test="evidence-agreed"]').text()).toBe(
      'Also reported by Wazuh, counted once.',
    )
  })

  it('says it in the plural, and leaves out what did not happen', async () => {
    const { wrapper } = await open({
      path: [
        chainStep({ duplicates: 3, evidence: [], stages: [] }),
        chainStep({ role: 'callout', incident_id: 12, duplicates: 0 }),
      ],
    })

    expect(wrapper.find('[data-test="step-duplicates"]').text()).toContain('3 alerts were')
    expect(wrapper.findAll('[data-test="step-evidence"]')).toHaveLength(1)
    expect(wrapper.findAll('[aria-label="How far it got"]')).toHaveLength(1)
  })

  it('shows the ports, and how many times an alert happened', async () => {
    const { wrapper } = await open()

    const [first] = wrapper.findAll('[data-test="evidence"]')
    expect(first?.text()).toContain('93.184.216.34')
    expect(first?.text()).toContain(':8080')
  })

  it('leaves out a port that the alert did not have, and counts repeats', async () => {
    const step = chainStep()
    const [item] = step.evidence
    if (!item) throw new Error('the step has evidence')
    const { wrapper } = await open({
      path: [
        {
          ...step,
          evidence: [
            { ...item, count: 12, duplicates: 0, signal: { ...item.signal, dst_port: null } },
          ],
        },
      ],
    })

    const shown = wrapper.find('[data-test="evidence"]').text()
    expect(shown).not.toContain(':null')
    expect(shown).toContain('12 times')
    expect(wrapper.find('[data-test="evidence-agreed"]').exists()).toBe(false)
  })

  it('shows only the first few pieces of evidence of a step', async () => {
    const step = chainStep()
    const [item] = step.evidence
    if (!item) throw new Error('the step has evidence')
    const { wrapper } = await open({
      path: [{ ...step, evidence: Array.from({ length: 9 }, () => item) }],
    })

    expect(wrapper.findAll('[data-test="evidence"]')).toHaveLength(6)
  })

  it('leads to the incident of each step', async () => {
    const { wrapper } = await open()

    expect(
      wrapper.findAll('[data-test="step-open"]').map((each) => each.attributes('href')),
    ).toEqual(['/incidents/11', '/incidents/12'])
  })

  it('draws no device where nothing called out', async () => {
    const { wrapper } = await open({ path: [chainStep()] })

    expect(wrapper.find('[data-test="path-device"]').exists()).toBe(false)
  })
})
