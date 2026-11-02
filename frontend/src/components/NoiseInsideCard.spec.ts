import { VSwitch } from 'vuetify/components'

import NoiseInsideCard from '@/components/NoiseInsideCard.vue'
import { mountWithPlugins } from '@/test/mount'

describe('NoiseInsideCard', () => {
  it('shows whether alerts between two devices are set aside, and says what is never set aside', async () => {
    const { wrapper } = await mountWithPlugins(NoiseInsideCard, { props: { modelValue: true } })

    expect(wrapper.findComponent(VSwitch).props('modelValue')).toBe(true)
    expect(wrapper.text()).toContain('Set aside alerts between two devices on my network')
    expect(wrapper.find('[data-test="inside-note"]').text()).toContain(
      "A program's ban is never set aside",
    )
  })

  it('tells the page what the switch is moved to', async () => {
    const { wrapper } = await mountWithPlugins(NoiseInsideCard, { props: { modelValue: false } })

    wrapper.findComponent(VSwitch).vm.$emit('update:modelValue', true)

    expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
  })
})
