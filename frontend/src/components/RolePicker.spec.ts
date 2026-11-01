import { ROLES } from '@/api/interfaces'
import RolePicker from '@/components/RolePicker.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(role: (typeof ROLES)[number] = 'home') {
  const chosen: string[] = []
  const mounted = await mountWithPlugins(RolePicker, {
    props: { modelValue: role, 'onUpdate:modelValue': (value: string) => chosen.push(value) },
  })
  return { ...mounted, chosen }
}

describe('RolePicker', () => {
  it('is one group of radio buttons, a card for each role with what it means', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('fieldset legend').text()).toBe('What is it for?')
    const cards = wrapper.findAll('label.role')
    expect(cards).toHaveLength(ROLES.length)
    expect(cards[0]!.text()).toContain('Internet')
    expect(cards[0]!.text()).toContain('the link to your provider')
    const inputs = wrapper.findAll('input[type="radio"]')
    expect(inputs).toHaveLength(ROLES.length)
    expect(new Set(inputs.map((input) => input.attributes('name'))).size).toBe(1)
  })

  it('marks the role that is chosen', async () => {
    const { wrapper } = await open('guest')

    const chosen = wrapper.findAll('.role--chosen')
    expect(chosen).toHaveLength(1)
    expect(chosen[0]!.attributes('data-test')).toBe('role-card-guest')
    expect((wrapper.find('input[value="guest"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('says which role was chosen', async () => {
    const { wrapper, chosen } = await open()

    await wrapper.find('input[value="iot"]').setValue(true)
    await flushPromises()

    expect(chosen).toEqual(['iot'])
  })
})
