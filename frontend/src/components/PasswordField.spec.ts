import { defineComponent, ref } from 'vue'

import PasswordField from '@/components/PasswordField.vue'
import { mountWithPlugins } from '@/test/mount'

async function open(creating = true) {
  const typed = ref('')
  const host = defineComponent({
    components: { PasswordField },
    setup: () => ({ typed }),
    template: `<PasswordField v-model="typed" label="Password" :creating="${String(creating)}" />`,
  })
  const { wrapper } = await mountWithPlugins(host)
  return { wrapper, typed, input: () => wrapper.find('input') }
}

describe('PasswordField', () => {
  it('hides what is typed, and names the field for password managers', async () => {
    const { input } = await open()
    expect(input().attributes('type')).toBe('password')
    expect(input().attributes('autocomplete')).toBe('new-password')
    expect(input().attributes('spellcheck')).toBe('false')
  })

  it('names the field for signing in when it is not for choosing a password', async () => {
    const { input } = await open(false)
    expect(input().attributes('autocomplete')).toBe('current-password')
  })

  it('passes what is typed on', async () => {
    const { input, typed } = await open()
    await input().setValue('a long enough phrase')
    expect(typed.value).toBe('a long enough phrase')
  })

  it('shows and hides what is typed, saying which with the button’s state', async () => {
    const { wrapper, input } = await open()
    const toggle = wrapper.find('[data-test="show-password"]')
    expect(toggle.attributes('aria-pressed')).toBe('false')

    await toggle.trigger('click')
    expect(input().attributes('type')).toBe('text')
    expect(toggle.attributes('aria-pressed')).toBe('true')

    await toggle.trigger('click')
    expect(input().attributes('type')).toBe('password')
  })
})
