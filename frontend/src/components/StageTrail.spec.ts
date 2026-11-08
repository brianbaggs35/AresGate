import StageTrail from '@/components/StageTrail.vue'
import { mountWithPlugins } from '@/test/mount'

describe('StageTrail', () => {
  it('lists the three steps and marks those the attack reached', async () => {
    const { wrapper } = await mountWithPlugins(StageTrail, {
      props: { stages: ['recon', 'access'] },
    })

    const reached = (stage: string) =>
      wrapper.find(`[data-test="stage-${stage}"]`).attributes('data-reached')
    expect([reached('recon'), reached('access'), reached('foothold')]).toEqual([
      'true',
      'true',
      'false',
    ])
    expect(wrapper.find('[data-test="stage-spoken"]').text()).toBe(
      'Got as far as: looking around, trying to get in.',
    )
  })

  it('says in words when it went no further than being seen', async () => {
    const { wrapper } = await mountWithPlugins(StageTrail, { props: { stages: [] } })

    expect(wrapper.find('[data-test="stage-spoken"]').text()).toBe(
      'No sign that it went further than being seen.',
    )
    expect(wrapper.find('[data-test="stage-recon"]').attributes('data-reached')).toBe('false')
  })
})
