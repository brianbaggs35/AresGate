import { VSelect } from 'vuetify/components'

import NoiseThinCard from '@/components/NoiseThinCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(modelValue = 1, defaultMinimum = 1) {
  const mounted = await mountWithPlugins(NoiseThinCard, {
    props: { modelValue, defaultMinimum },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const select = () => mounted.wrapper.findComponent(VSelect)
  return { ...mounted, find, select }
}

describe('NoiseThinCard', () => {
  it('says that one is no minimum at all, and has no reset to make', async () => {
    const { find, select } = await show()

    expect(select().props('modelValue')).toBe(1)
    expect(find('thin-sentence').text()).toContain('No minimum')
    expect(find('thin-reset').exists()).toBe(false)
  })

  it('says how many low alerts an incident needs, and goes back to the default on request', async () => {
    const { find, wrapper } = await show(3, 1)

    expect(find('thin-sentence').text()).toContain('once it has 3 of them')

    await find('thin-reset').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([[1]])
  })

  it('tells the page the choice that is made', async () => {
    const { select, wrapper } = await show()

    select().vm.$emit('update:modelValue', 5)

    expect(wrapper.emitted('update:modelValue')).toEqual([[5]])
  })
})
