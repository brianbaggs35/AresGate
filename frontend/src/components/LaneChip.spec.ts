import LaneChip from '@/components/LaneChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('LaneChip', () => {
  it.each([
    ['threat', 'Threat', 'Highly likely'],
    ['suspect', 'Suspect', 'Worth a look'],
    ['background', 'Background', 'out of your way'],
  ] as const)('names the %s lane and says what it means', async (lane, label, meaning) => {
    const { wrapper } = await mountWithPlugins(LaneChip, { props: { lane } })

    const chip = wrapper.find('[data-test="lane-chip"]')
    expect(chip.text()).toBe(label)
    expect(chip.attributes('title')).toContain(meaning)
  })

  it('draws the background lane as an outline, quieter than the others', async () => {
    const quiet = await mountWithPlugins(LaneChip, { props: { lane: 'background' } })
    const loud = await mountWithPlugins(LaneChip, { props: { lane: 'threat' } })

    expect(quiet.wrapper.find('[data-test="lane-chip"]').classes()).toContain(
      'v-chip--variant-outlined',
    )
    expect(loud.wrapper.find('[data-test="lane-chip"]').classes()).toContain('v-chip--variant-flat')
  })
})
