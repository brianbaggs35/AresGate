import { VSlider } from 'vuetify/components'

import * as usageApi from '@/api/aiUsage'
import { ApiError } from '@/api/client'
import AiLevelCard from '@/components/AiLevelCard.vue'
import { levels } from '@/test/aiUsage'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function show(level: usageApi.UsageLevel['key'] = 'medium') {
  const save = vi.spyOn(usageApi, 'saveLevel')
  const mounted = await mountWithPlugins(AiLevelCard, {
    signedIn: 'admin',
    props: { level, levels: levels() },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const slider = () => mounted.wrapper.findComponent(VSlider)
  const move = async (to: number) => {
    slider().vm.$emit('update:modelValue', to)
    await flushPromises()
  }
  const emitted = () => mounted.wrapper.emitted('changed')
  return { ...mounted, save, find, slider, move, emitted }
}

describe('AiLevelCard', () => {
  it('starts where the level is kept, and says what that level does', async () => {
    const { find, slider } = await show('medium')

    expect(slider().props('modelValue')).toBe(2)
    expect(slider().props('max')).toBe(4)
    expect(find('level-name').text()).toBe('Medium')
    expect(find('level-rate').text()).toBe('Up to 20 an hour')
    expect(find('level-summary').text()).toBe(
      'Reads incidents rated medium or higher, up to 20 an hour.',
    )
    expect(find('level-save').attributes('disabled')).toBeDefined()
  })

  it('says what a level does as the slider moves, and says the lowest reads nothing by itself', async () => {
    const { find, move } = await show()

    await move(0)

    expect(find('level-name').text()).toBe('Very low')
    expect(find('level-rate').text()).toBe('Nothing by itself')
    expect(find('level-summary').text()).toContain('answers only when you ask')

    await move(4)

    expect(find('level-name').text()).toBe('Maximum')
    expect(find('level-rate').text()).toBe('Up to 150 an hour')
  })

  it('names the level, not its number, for a screen reader', async () => {
    const { slider } = await show()
    const spoken = slider().props('valueFormat') as (found: { value: number }) => string

    expect(spoken({ value: 3 })).toBe('High')
  })

  it('can be saved only once it has moved, and moving back is no change', async () => {
    const { find, move } = await show()

    await move(3)
    expect(find('level-save').attributes('disabled')).toBeUndefined()

    await move(2)
    expect(find('level-save').attributes('disabled')).toBeDefined()
  })

  it('keeps the level with the security token, and tells the page', async () => {
    const { find, move, save, emitted } = await show()
    save.mockResolvedValue({ level: 'high' })

    await move(3)
    await find('level-save').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('high', 'a-security-token')
    expect(emitted()?.[0]).toEqual(['high'])
    expect(find('level-saved').text()).toBe('Saved.')
  })

  it('withdraws the note that it was saved when the slider moves again', async () => {
    const { find, move, save, wrapper } = await show()
    save.mockResolvedValue({ level: 'high' })
    await move(3)
    await find('level-save').trigger('click')
    await flushPromises()
    await wrapper.setProps({ level: 'high' })
    expect(find('level-saved').exists()).toBe(true)

    await move(1)

    expect(find('level-saved').exists()).toBe(false)
  })

  it('follows the level when the page asks again', async () => {
    const { slider, wrapper, find } = await show('medium')

    await wrapper.setProps({ level: 'low' })

    expect(slider().props('modelValue')).toBe(1)
    expect(find('level-name').text()).toBe('Low')
  })

  it('says so when the level could not be kept, and tells the page nothing', async () => {
    const { find, move, save, emitted } = await show()
    save.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))

    await move(1)
    await find('level-save').trigger('click')
    await flushPromises()

    expect(find('level-failure').text()).toBe("Can't reach AresGate.")
    expect(find('level-saved').exists()).toBe(false)
    expect(emitted()).toBeUndefined()
  })
})
