import ClearingTrail from '@/components/ClearingTrail.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ClearingTrail', () => {
  it('is not there for an incident the AI had no say in', async () => {
    const { wrapper } = await mountWithPlugins(ClearingTrail, { props: { steps: [] } })

    expect(wrapper.find('[data-test="clearing-trail"]').exists()).toBe(false)
  })

  it('tells what happened, in order', async () => {
    const { wrapper } = await mountWithPlugins(ClearingTrail, {
      props: {
        steps: [
          {
            action: 'cleared',
            at: '2026-06-01T12:00:00Z',
            by: 'the AI',
            verdict: 'not_suspicious',
            confidence: 91,
          },
          {
            action: 'taken_back',
            at: '2026-06-01T13:00:00Z',
            by: 'brian',
            verdict: null,
            confidence: null,
          },
        ],
      },
    })

    const lines = wrapper.findAll('[data-test="clearing-steps"] li')
    expect(lines).toHaveLength(2)
    expect(lines[0]?.text()).toContain('The AI cleared this as not suspicious (91% sure).')
    expect(lines[1]?.text()).toContain('brian took back what the AI cleared.')
  })
})
