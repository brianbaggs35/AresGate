import AgentTimeline from '@/components/AgentTimeline.vue'
import { runDetail, step } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(steps = runDetail().steps, live = false) {
  const mounted = await mountWithPlugins(AgentTimeline, { props: { steps, live } })
  return {
    ...mounted,
    find: (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`),
  }
}

describe('AgentTimeline', () => {
  it('lists each step in order, with the part of the graph it belongs to', async () => {
    const { wrapper } = await open()

    const titles = wrapper.findAll('[data-test="step-title"]').map((title) => title.text())
    expect(titles).toEqual([
      'Planned what to look at first: open incidents',
      'Looked at open incidents',
      'Asked Anthropic',
      'Wrote the report',
    ])
    expect(wrapper.findAll('[data-test="timeline-step"]')[1]!.text()).toContain('Look ·')
  })

  it('says what a step summed up, and lets what it saw be opened', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="step-summary"]').text()).toBe('2 open incidents')
    expect(wrapper.findAll('[data-test="step-more"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="step-more"] summary').text()).toBe('What it saw (2)')
    expect(wrapper.findAll('[data-test="step-line"]').map((line) => line.text())).toEqual([
      'Incident 4: scan',
      'Incident 5: login',
    ])
  })

  it('says it is still working while the run is going', async () => {
    const { find } = await open([step()], true)

    expect(find('timeline-working').text()).toContain('Working on the next step')
  })

  it('does not say it while the run is over', async () => {
    const { find } = await open([step()], false)

    expect(find('timeline-working').exists()).toBe(false)
  })

  it('says there was nothing to keep when a run that is over has no steps', async () => {
    const { find } = await open([], false)

    expect(find('timeline-empty').text()).toBe('No steps were kept for this run.')
  })

  it('shows only the working line for a run that has just begun', async () => {
    const { wrapper, find } = await open([], true)

    expect(wrapper.findAll('[data-test="timeline-step"]')).toHaveLength(0)
    expect(find('timeline-working').exists()).toBe(true)
    expect(find('timeline-empty').exists()).toBe(false)
  })

  it('says how long each step took, until the next began, and not for the last', async () => {
    const { wrapper } = await open([
      step({ at: '2026-11-10T12:00:00Z' }),
      step({ seq: 2, at: '2026-11-10T12:00:02.500Z' }),
    ])

    const took = wrapper.findAll('[data-test="step-took"]')
    expect(took).toHaveLength(1)
    expect(took[0]!.text()).toBe('· took 2.5 s')
  })

  it('links each incident a step looked at, and says how many lines it did not keep', async () => {
    const { wrapper } = await open([
      step({
        node: 'act',
        detail: {
          lines: ['Incident 4: scan'],
          more: 3,
          refs: [
            { kind: 'incident', key: '4', label: 'Incident 4' },
            { kind: 'device', key: 'x', label: 'A device' },
            { kind: 'incident' },
            'nonsense',
          ],
        },
      }),
    ])

    const refs = wrapper.findAll('[data-test="step-ref"]')
    expect(refs.map((ref) => ref.text())).toEqual(['Incident 4', 'A device'])
    expect(refs[0]!.attributes('href')).toBe('/incidents/4')
    expect(refs[1]!.attributes('href')).toBeUndefined()
    expect(wrapper.find('[data-test="step-rest"]').text()).toBe('And 3 more it did not keep.')
  })

  it('shows neither when the step has no refs and kept every line', async () => {
    const { wrapper } = await open([step({ detail: { lines: ['One'], refs: 'none' } })])

    expect(wrapper.find('[data-test="step-refs"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="step-rest"]').exists()).toBe(false)
  })
})
