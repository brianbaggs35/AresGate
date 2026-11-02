import ChoiceToggle from '@/components/ChoiceToggle.vue'
import { mountWithPlugins } from '@/test/mount'

const OPTIONS = [
  { key: 'a', label: 'First' },
  { key: 'b', label: 'Second' },
] as const

async function show(value: 'a' | 'b' = 'a') {
  return mountWithPlugins(ChoiceToggle, {
    props: { modelValue: value, options: OPTIONS, label: 'Which one', name: 'which' },
  })
}

describe('ChoiceToggle', () => {
  it('is a named group of buttons, one for each option, and says which is chosen', async () => {
    const { wrapper } = await show('b')
    const group = wrapper.find('[data-test="which"]')

    expect(group.attributes('aria-label')).toBe('Which one')
    expect(wrapper.findAll('button').map((button) => button.text())).toEqual(['First', 'Second'])
    expect(wrapper.find('[data-test="which-a"]').classes()).not.toContain('v-btn--active')
    expect(wrapper.find('[data-test="which-b"]').classes()).toContain('v-btn--active')
  })

  it('says which option was chosen when one is pressed', async () => {
    const { wrapper } = await show('a')

    await wrapper.find('[data-test="which-b"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['b']])
  })

  it('keeps one chosen when the chosen one is pressed again', async () => {
    const { wrapper } = await show('a')

    await wrapper.find('[data-test="which-a"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
