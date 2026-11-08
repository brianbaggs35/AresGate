import { VRadioGroup, VTextarea, VTextField } from 'vuetify/components'

import ThreatNetworkCard from '@/components/ThreatNetworkCard.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(ThreatNetworkCard, {
    props: { exposure: 'some', ports: [22, 443], notes: '', maxPorts: 3, maxNotes: 500, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const ports = () => mounted.wrapper.findComponent(VTextField)
  return { ...mounted, find, ports }
}

describe('ThreatNetworkCard', () => {
  it('offers what can be open, and asks which ports when some are', async () => {
    const { find, ports, wrapper } = await show()

    expect(wrapper.findComponent(VRadioGroup).props('modelValue')).toBe('some')
    expect(['none', 'some', 'unknown'].every((name) => find(`exposure-${name}`).exists())).toBe(
      true,
    )
    expect(ports().props('modelValue')).toBe('22, 443')
  })

  it('does not ask which ports when none are open or it is not known', async () => {
    for (const exposure of ['none', 'unknown']) {
      const { find } = await show({ exposure })
      expect(find('threat-ports').exists()).toBe(false)
    }
  })

  it('tells the page what is chosen', async () => {
    const { wrapper } = await show()

    wrapper.findComponent(VRadioGroup).vm.$emit('update:modelValue', 'none')
    wrapper.findComponent(VTextarea).vm.$emit('update:modelValue', 'A web server')
    wrapper.findComponent(VTextarea).vm.$emit('update:modelValue', null)

    expect(wrapper.emitted('update:exposure')).toEqual([['none']])
    expect(wrapper.emitted('update:notes')).toEqual([['A web server'], ['']])
  })

  it('reads the ports as they are typed', async () => {
    const { ports, wrapper } = await show()

    ports().vm.$emit('update:modelValue', '80, 22 443')

    expect(wrapper.emitted('update:ports')).toEqual([[[22, 80, 443]]])
    expect(ports().props('errorMessages')).toBe('')
  })

  it('takes an emptied field as no ports', async () => {
    const { ports, wrapper } = await show()

    ports().vm.$emit('update:modelValue', null)

    expect(wrapper.emitted('update:ports')).toEqual([[[]]])
  })

  it('says which words are not ports, and keeps what was kept until they are', async () => {
    const { ports, wrapper } = await show()

    ports().vm.$emit('update:modelValue', '22, http')
    await wrapper.vm.$nextTick()
    expect(ports().props('errorMessages')).toBe('http is not a port number (1 to 65535).')

    ports().vm.$emit('update:modelValue', '22, http, 0')
    await wrapper.vm.$nextTick()
    expect(ports().props('errorMessages')).toBe('http, 0 are not a port number (1 to 65535).')
    expect(wrapper.emitted('update:ports')).toBeUndefined()
  })

  it('does not take more ports than there is room for', async () => {
    const { ports, wrapper } = await show()

    ports().vm.$emit('update:modelValue', '1 2 3 4')
    await wrapper.vm.$nextTick()

    expect(ports().props('errorMessages')).toBe('At most 3 ports.')
    expect(wrapper.emitted('update:ports')).toBeUndefined()
  })

  it('says the ports again when they are changed from outside, as when changes are discarded', async () => {
    const { ports, wrapper } = await show()
    ports().vm.$emit('update:modelValue', '22, http')
    await wrapper.vm.$nextTick()

    await wrapper.setProps({ ports: [22, 443, 8080] })
    expect(ports().props('modelValue')).toBe('22, 443, 8080')
    expect(ports().props('errorMessages')).toBe('')

    // The page saying what the field already says leaves what is being typed alone.
    ports().vm.$emit('update:modelValue', '1, 2')
    await wrapper.setProps({ ports: [1, 2] })
    expect(ports().props('modelValue')).toBe('1, 2')
  })
})
