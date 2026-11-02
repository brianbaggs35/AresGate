import { VSlider } from 'vuetify/components'

import NoiseFloorCard from '@/components/NoiseFloorCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(modelValue = 35) {
  const mounted = await mountWithPlugins(NoiseFloorCard, {
    props: { modelValue, defaultFloor: 35, mediumFrom: 35, highFrom: 65 },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const slider = () => mounted.wrapper.findComponent(VSlider)
  return { ...mounted, find, slider }
}

describe('NoiseFloorCard', () => {
  it('says where the floor is, in a number and a word, and what that means', async () => {
    const { find, slider } = await show()

    expect(find('floor-value').text()).toBe('35 out of 100 (medium)')
    expect(slider().props('modelValue')).toBe(35)
    expect(slider().props('min')).toBe(5)
    expect(slider().props('max')).toBe(95)
    expect(slider().props('step')).toBe(5)
    expect(find('floor-sentence').text()).toContain('at least 35 sure it is real')
  })

  it('names the number and the word for a screen reader', async () => {
    const { slider } = await show()
    const spoken = slider().props('valueFormat') as (found: { value: number }) => string

    expect(spoken({ value: 70 })).toBe('70, high confidence')
  })

  it('tells the page where the slider is moved to', async () => {
    const { slider, wrapper } = await show()

    slider().vm.$emit('update:modelValue', 60)

    expect(wrapper.emitted('update:modelValue')).toEqual([[60]])
  })

  it('offers to go back to the default once it is another, and not before', async () => {
    const { find } = await show()
    expect(find('floor-reset').exists()).toBe(false)

    const other = await show(60)
    expect(other.find('floor-reset').text()).toBe('Back to 35')

    await other.find('floor-reset').trigger('click')

    expect(other.wrapper.emitted('update:modelValue')).toEqual([[35]])
  })
})
