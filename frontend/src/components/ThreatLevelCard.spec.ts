import { VSlider } from 'vuetify/components'

import ThreatLevelCard from '@/components/ThreatLevelCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(modelValue = 65) {
  const mounted = await mountWithPlugins(ThreatLevelCard, {
    props: { modelValue, defaultValue: 65 },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const slider = () => mounted.wrapper.findComponent(VSlider)
  return { ...mounted, find, slider }
}

describe('ThreatLevelCard', () => {
  it('says where the bar is, in a number, and what that means', async () => {
    const { find, slider } = await show()

    expect(find('threat-value').text()).toBe('65 out of 100')
    expect(slider().props('modelValue')).toBe(65)
    expect(slider().props('min')).toBe(5)
    expect(slider().props('max')).toBe(100)
    expect(slider().props('step')).toBe(5)
    expect(find('threat-sentence').text()).toContain('at least 65 out of 100 sure')
  })

  it('names the number for a screen reader', async () => {
    const { slider } = await show()
    const spoken = slider().props('valueFormat') as (found: { value: number }) => string

    expect(spoken({ value: 70 })).toBe('70 out of 100')
  })

  it('tells the page where the slider is moved to', async () => {
    const { slider, wrapper } = await show()

    slider().vm.$emit('update:modelValue', 80)

    expect(wrapper.emitted('update:modelValue')).toEqual([[80]])
  })

  it('offers to go back to the default once it is another, and not before', async () => {
    const { find } = await show()
    expect(find('threat-reset').exists()).toBe(false)

    const other = await show(80)
    expect(other.find('threat-reset').text()).toBe('Back to 65')

    await other.find('threat-reset').trigger('click')

    expect(other.wrapper.emitted('update:modelValue')).toEqual([[65]])
  })
})
