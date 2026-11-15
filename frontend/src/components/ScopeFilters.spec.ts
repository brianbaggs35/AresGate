import { VSelect } from 'vuetify/components'

import * as interfacesApi from '@/api/interfaces'
import ScopeFilters from '@/components/ScopeFilters.vue'
import { iface, listing } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function mountScope(search = '', interfaces: string[] | Error = ['Internet', 'Guests']) {
  const list = vi.spyOn(interfacesApi, 'fetchInterfaces')
  if (interfaces instanceof Error) list.mockRejectedValue(interfaces)
  else {
    list.mockResolvedValue(
      listing({ interfaces: interfaces.map((name, id) => iface({ id: id + 1, name })) }),
    )
  }
  const mounted = await mountWithPlugins(ScopeFilters, {
    signedIn: 'brian',
    props: { modelValue: search },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const said = () => mounted.wrapper.emitted('update:modelValue')?.map(([text]) => text) ?? []
  const pick = async (selector: string, value: string | null) => {
    mounted.wrapper
      .findComponent<typeof VSelect>(`[data-test="${selector}"]`)
      .vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  const type = async (selector: string, value: string) => {
    await find(selector).find('input').setValue(value)
  }
  return { ...mounted, find, said, pick, type }
}

describe('ScopeFilters', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows any time, no dates, no device and no interface for a search that says nothing of them', async () => {
    const { find, wrapper } = await mountScope('ssh')

    expect(find('scope-when').text()).toContain('Any time')
    expect(find('scope-from').exists()).toBe(false)
    expect(wrapper.find<HTMLInputElement>('[data-test="scope-device"] input').element.value).toBe(
      '',
    )
    expect(find('scope-interface').exists()).toBe(true)
  })

  it('puts a time in the search, in place of the one that was there, and takes it out for any time', async () => {
    const { pick, said } = await mountScope('ssh since:1h')

    await pick('scope-when', '7d')
    await pick('scope-when', 'any')

    expect(said()).toEqual(['ssh since:7d', 'ssh'])
  })

  it('drops an end as well when a time since is chosen', async () => {
    const { pick, said } = await mountScope('before:2026-11-02 since:2026-11-01')

    await pick('scope-when', 'today')

    expect(said()).toEqual(['since:today'])
  })

  it('reads the time a search says as the choice, in any case', async () => {
    const { find } = await mountScope('since:24H')

    expect(find('scope-when').text()).toContain('The last 24 hours')
  })

  it('asks for two dates once dates are chosen, and says nothing until one is picked', async () => {
    const { find, pick, said } = await mountScope('')

    await pick('scope-when', 'custom')

    expect(find('scope-from').exists()).toBe(true)
    expect(find('scope-until').exists()).toBe(true)
    expect(said()).toEqual([])
  })

  it('writes the first day and the day after the last, which the search ends before', async () => {
    const { pick, said, type } = await mountScope('ssh')
    await pick('scope-when', 'custom')

    await type('scope-from', '2026-11-01')
    await pick('scope-until', '2026-11-30')
    await pick('scope-until', '2026-12-31')

    expect(said()).toEqual([
      'ssh since:2026-11-01',
      'ssh before:2026-12-01',
      'ssh before:2027-01-01',
    ])
  })

  it('shows the days of a search that gives dates, the last as it is said to a person', async () => {
    const { wrapper, find } = await mountScope('since:2026-11-01 before:2026-12-01')

    expect(find('scope-when').text()).toContain('Choose dates')
    expect(wrapper.find<HTMLInputElement>('[data-test="scope-from"] input').element.value).toBe(
      '2026-11-01',
    )
    expect(wrapper.find<HTMLInputElement>('[data-test="scope-until"] input').element.value).toBe(
      '2026-11-30',
    )
  })

  it('takes a day out of the search when it is cleared', async () => {
    const { pick, said } = await mountScope('since:2026-11-01 before:2026-12-01')

    await pick('scope-from', null)
    await pick('scope-until', null)

    expect(said()).toEqual(['before:2026-12-01', 'since:2026-11-01'])
  })

  it('says a time it cannot choose is set in the search, and keeps it until another is chosen', async () => {
    const { find, pick, said } = await mountScope('since:2026-11-01T08:00 before:2026-11-01T09:00')

    expect(find('scope-when').text()).toContain('Set in the search')
    expect(find('scope-from').exists()).toBe(false)

    await pick('scope-when', 'other')
    expect(said()).toEqual([])

    await pick('scope-when', '1h')
    expect(said()).toEqual(['since:1h'])
  })

  it('says dates are not chosen when a day is mixed with a time or there are too many', async () => {
    const mixed = await mountScope('since:2026-11-01 before:6h')
    expect(mixed.find('scope-when').text()).toContain('Set in the search')
    mixed.wrapper.unmount()

    const many = await mountScope('since:2026-11-01 since:2026-11-02 before:2026-11-03')
    expect(many.find('scope-when').text()).toContain('Set in the search')
  })

  it('puts a device in the search when Enter is pressed, quoted if it has several words', async () => {
    const { find, said, type } = await mountScope('ssh')

    await type('scope-device', 'living room tv')
    await find('scope-device').find('input').trigger('keydown', { key: 'Enter' })

    expect(said()).toEqual(['ssh device:"living room tv"'])
  })

  it('puts a device in the search when the box is left, and says nothing if it did not change', async () => {
    const { find, said, type } = await mountScope('device:nas')

    await type('scope-device', 'nas')
    await find('scope-device').find('input').trigger('blur')
    await type('scope-device', 'printer')
    await find('scope-device').find('input').trigger('blur')

    expect(said()).toEqual(['device:printer'])
  })

  it('does nothing when the box is left unchanged', async () => {
    const { find, said } = await mountScope('device:nas')

    await find('scope-device').find('input').trigger('blur')

    expect(said()).toEqual([])
  })

  it('shows the device the search names, and takes it out when the box is cleared', async () => {
    const { wrapper, find, said, pick } = await mountScope('ssh device:"living room tv"')
    expect(wrapper.find<HTMLInputElement>('[data-test="scope-device"] input').element.value).toBe(
      'living room tv',
    )

    await find('scope-device').find('.v-field__clearable .v-icon').trigger('click')
    await flushPromises()
    await pick('scope-device', null)

    expect(said()).toEqual(['ssh'])
  })

  it('puts an interface in the search, and takes it out when it is cleared', async () => {
    const { pick, said } = await mountScope('ssh interface:Internet')

    await pick('scope-interface', 'Guests')
    await pick('scope-interface', null)

    expect(said()).toEqual(['ssh interface:Guests', 'ssh'])
  })

  it('offers the interface a search names even when it is not one of yours', async () => {
    const { find } = await mountScope('interface:Cellar', ['Internet'])

    expect(find('scope-interface').text()).toContain('Cellar')
  })

  it('offers no interface while none is named', async () => {
    const { find } = await mountScope('', [])

    expect(find('scope-interface').exists()).toBe(false)
  })

  it('works without the interfaces when they cannot be read', async () => {
    const { find } = await mountScope('', new Error('boom'))

    expect(find('scope-interface').exists()).toBe(false)
    expect(find('scope-when').exists()).toBe(true)
  })
})
