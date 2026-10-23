import { defineComponent, ref } from 'vue'

import type { Module } from '@/api/integrations'
import ModuleList from '@/components/ModuleList.vue'
import { module } from '@/test/integrations'
import { mountWithPlugins } from '@/test/mount'

async function open(modules: Module[], disabled: string[] = []) {
  const off = ref(disabled)
  const host = defineComponent({
    components: { ModuleList },
    setup: () => ({ modules, off }),
    template: '<ModuleList v-model="off" :modules="modules" id-prefix="api" />',
  })
  const { wrapper } = await mountWithPlugins(host)
  const rows = () => wrapper.findAll('[data-test="module"]')
  return { wrapper, off, rows }
}

describe('ModuleList', () => {
  it('lists the services, with what each gives', async () => {
    const { rows } = await open([
      module({ key: 'suricata', label: 'Suricata', summary: 'Intrusion alerts.' }),
      module({ key: 'crowdsec', label: 'CrowdSec', summary: 'Banned addresses.' }),
    ])
    expect(rows()).toHaveLength(2)
    expect(rows()[0]?.find('[data-test="module-name"]').text()).toBe('Suricata')
    expect(rows()[0]?.text()).toContain('Intrusion alerts.')
  })

  it('is a section named Services', async () => {
    const { wrapper } = await open([module({ key: 'a', label: 'A' })])
    const section = wrapper.find('section')
    const heading = wrapper.find(`#${section.attributes('aria-labelledby')}`)
    expect(heading.text()).toBe('Services')
  })

  it('asks for a test while none of them has been looked for', async () => {
    const { wrapper, rows } = await open([module({ key: 'a', label: 'A' })])
    expect(wrapper.find('[data-test="modules-help"]').text()).toContain('Test the connection')
    expect(rows()[0]?.find('[data-test="module-state"]').exists()).toBe(false)
  })

  it('says what testing found, in words', async () => {
    const { wrapper, rows } = await open([
      module({ key: 'a', label: 'A', state: 'running' }),
      module({ key: 'b', label: 'B', state: 'not_installed' }),
    ])
    expect(wrapper.find('[data-test="modules-help"]').text()).toContain('What testing found')
    expect(rows().map((row) => row.find('[data-test="module-state"]').text())).toEqual([
      'Running',
      'Not installed',
    ])
  })

  it('has every service switched on unless it was switched off', async () => {
    const { rows } = await open(
      [module({ key: 'a', label: 'A' }), module({ key: 'b', label: 'B' })],
      ['b'],
    )
    const on = rows().map((row) => row.find<HTMLInputElement>('input').element.checked)
    expect(on).toEqual([true, false])
  })

  it('names each switch for what it does', async () => {
    const { rows } = await open([module({ key: 'suricata', label: 'Suricata' })])
    expect(rows()[0]?.find('input').attributes('aria-label')).toBe('Read Suricata')
  })

  it('switches a service off and on again', async () => {
    const { rows, off } = await open([
      module({ key: 'a', label: 'A' }),
      module({ key: 'b', label: 'B' }),
    ])
    await rows()[1]?.find('input').setValue(false)
    expect(off.value).toEqual(['b'])
    await rows()[0]?.find('input').setValue(false)
    expect(off.value).toEqual(['b', 'a'])
    await rows()[1]?.find('input').setValue(true)
    expect(off.value).toEqual(['a'])
  })

  it('has no use for a switch on a service that is not installed', async () => {
    const { rows } = await open([
      module({ key: 'a', label: 'A', state: 'not_installed' }),
      module({ key: 'b', label: 'B', state: 'stopped' }),
    ])
    expect(rows()[0]?.find('input').attributes('disabled')).toBeDefined()
    expect(rows()[1]?.find('input').attributes('disabled')).toBeUndefined()
  })
})
