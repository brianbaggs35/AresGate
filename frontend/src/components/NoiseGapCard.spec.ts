import { VSelect } from 'vuetify/components'

import NoiseGapCard from '@/components/NoiseGapCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: { scanHours?: number; bruteForceHours?: number } = {}) {
  const mounted = await mountWithPlugins(NoiseGapCard, {
    props: {
      scanHours: 4,
      bruteForceHours: 6,
      defaultScanHours: 4,
      defaultBruteForceHours: 6,
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const selects = () => mounted.wrapper.findAllComponents(VSelect)
  return { ...mounted, find, selects }
}

describe('NoiseGapCard', () => {
  it('says how long a scan and a brute force may go quiet, in hours', async () => {
    const { find, selects } = await show({ scanHours: 8 })

    expect(selects()).toHaveLength(2)
    expect(selects()[0]?.props('modelValue')).toBe(8)
    expect(selects()[1]?.props('modelValue')).toBe(6)
    expect(find('gap-sentence').text()).toContain('less than 8 hours')
    expect(find('gap-sentence').text()).toContain('less than 6 hours')
  })

  it('has no reset while they are as they were', async () => {
    const { find } = await show()

    expect(find('gap-reset').exists()).toBe(false)
  })

  it('goes back to the defaults on request', async () => {
    const { find, wrapper } = await show({ scanHours: 8, bruteForceHours: 2 })

    await find('gap-reset').trigger('click')

    expect(wrapper.emitted('update:scanHours')).toEqual([[4]])
    expect(wrapper.emitted('update:bruteForceHours')).toEqual([[6]])
  })

  it('tells the page each choice that is made', async () => {
    const { selects, wrapper } = await show()

    selects()[0]?.vm.$emit('update:modelValue', 12)
    selects()[1]?.vm.$emit('update:modelValue', 3)

    expect(wrapper.emitted('update:scanHours')).toEqual([[12]])
    expect(wrapper.emitted('update:bruteForceHours')).toEqual([[3]])
  })
})
