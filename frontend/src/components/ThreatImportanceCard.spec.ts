import { VSlider } from 'vuetify/components'

import ThreatImportanceCard from '@/components/ThreatImportanceCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(ThreatImportanceCard, {
    props: { drop: 10, raise: 0, defaultDrop: 10, defaultRaise: 0, max: 30, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const sliders = () => mounted.wrapper.findAllComponents(VSlider)
  return { ...mounted, find, sliders }
}

describe('ThreatImportanceCard', () => {
  it('says how far each moves the bar, and what that means', async () => {
    const { find, sliders } = await show({ drop: 15, raise: 5 })

    expect(find('importance-drop-value').text()).toBe('Important devices: 15 points lower')
    expect(find('importance-raise-value').text()).toBe('Guests and IoT devices: 5 points higher')
    expect(find('importance-drop-sentence').text()).toContain('15 points less sure')
    expect(find('importance-raise-sentence').text()).toContain('5 points more')
    expect(sliders().map((slider) => slider.props('max'))).toEqual([30, 30])
    expect(sliders().map((slider) => slider.props('min'))).toEqual([0, 0])
  })

  it('names the number for a screen reader', async () => {
    const { sliders } = await show()
    const spoken = sliders()[0]?.props('valueFormat') as (found: { value: number }) => string

    expect(spoken({ value: 12 })).toBe('12 points')
  })

  it('tells the page where either slider is moved to', async () => {
    const { sliders, wrapper } = await show()

    sliders()[0]?.vm.$emit('update:modelValue', 20)
    sliders()[1]?.vm.$emit('update:modelValue', 10)

    expect(wrapper.emitted('update:drop')).toEqual([[20]])
    expect(wrapper.emitted('update:raise')).toEqual([[10]])
  })

  it('offers to go back to the default once it is another, and not before', async () => {
    const quiet = await show()
    expect(quiet.find('importance-drop-reset').exists()).toBe(false)
    expect(quiet.find('importance-raise-reset').exists()).toBe(false)

    const moved = await show({ drop: 0, raise: 20 })
    expect(moved.find('importance-drop-reset').text()).toBe('Back to 10')
    expect(moved.find('importance-raise-reset').text()).toBe('Back to 0')
    await moved.find('importance-drop-reset').trigger('click')
    await moved.find('importance-raise-reset').trigger('click')

    expect(moved.wrapper.emitted('update:drop')).toEqual([[10]])
    expect(moved.wrapper.emitted('update:raise')).toEqual([[0]])
  })
})
