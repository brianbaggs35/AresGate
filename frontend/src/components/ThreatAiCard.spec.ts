import { VSlider, VSwitch } from 'vuetify/components'

import ThreatAiCard from '@/components/ThreatAiCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(ThreatAiCard, {
    props: {
      mayClear: true,
      clearFrom: 80,
      confirms: true,
      givesVerdicts: false,
      defaultClearFrom: 80,
      minClearFrom: 50,
      watching: true,
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ThreatAiCard', () => {
  it('says what the AI may do and how sure it has to be', async () => {
    const { find, wrapper } = await show()

    expect(find('clear-value').text()).toBe('80% sure')
    expect(find('clear-sentence').text()).toContain('at least 80% sure')
    expect(wrapper.findComponent(VSlider).props('min')).toBe(50)
    expect(find('threat-ai-off').exists()).toBe(false)
  })

  it('names the number for a screen reader', async () => {
    const { wrapper } = await show()
    const spoken = wrapper.findComponent(VSlider).props('valueFormat') as (found: {
      value: number
    }) => string

    expect(spoken({ value: 90 })).toBe('90 percent sure')
  })

  it('leaves out how sure while the AI may not set things aside', async () => {
    const { find } = await show({ mayClear: false })

    expect(find('threat-clear-bar').exists()).toBe(false)
  })

  it('says none of it does anything while no AI is watching', async () => {
    const { find } = await show({ watching: false })

    expect(find('threat-ai-off').text()).toContain('No AI is watching')
    expect(find('threat-ai-link').attributes('href')).toBe('/settings/ai')
  })

  it('tells the page what is changed', async () => {
    const { wrapper } = await show()
    const [clear, confirm, verdicts] = wrapper.findAllComponents(VSwitch)

    clear?.vm.$emit('update:modelValue', false)
    confirm?.vm.$emit('update:modelValue', null)
    verdicts?.vm.$emit('update:modelValue', true)
    wrapper.findComponent(VSlider).vm.$emit('update:modelValue', 90)

    expect(wrapper.emitted('update:mayClear')).toEqual([[false]])
    expect(wrapper.emitted('update:confirms')).toEqual([[false]])
    expect(wrapper.emitted('update:givesVerdicts')).toEqual([[true]])
    expect(wrapper.emitted('update:clearFrom')).toEqual([[90]])
  })

  it('says the AI gives verdicts only when you let it, and that they can be taken back', async () => {
    const { wrapper } = await show()

    expect(wrapper.text()).toContain('Let the AI clear false positives')
    expect(wrapper.text()).toContain('you can take it back there')
  })

  it('offers to go back to the default once it is another, and not before', async () => {
    const { find } = await show()
    expect(find('clear-reset').exists()).toBe(false)

    const other = await show({ clearFrom: 95 })
    expect(other.find('clear-reset').text()).toBe('Back to 80')

    await other.find('clear-reset').trigger('click')

    expect(other.wrapper.emitted('update:clearFrom')).toEqual([[80]])
  })
})
