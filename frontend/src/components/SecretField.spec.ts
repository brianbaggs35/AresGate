import { defineComponent, ref } from 'vue'

import SecretField from '@/components/SecretField.vue'
import { mountWithPlugins } from '@/test/mount'

async function open(saved = false, hint?: string) {
  const typed = ref('')
  const host = defineComponent({
    components: { SecretField },
    setup: () => ({ typed, saved, hint }),
    template: '<SecretField v-model="typed" label="API key" :saved="saved" :hint="hint" />',
  })
  const { wrapper } = await mountWithPlugins(host)
  return { wrapper, typed, input: () => wrapper.find('input') }
}

describe('SecretField', () => {
  it('hides what is typed and keeps password managers and spellcheck out of it', async () => {
    const { input } = await open()
    expect(input().attributes('type')).toBe('password')
    expect(input().attributes('autocomplete')).toBe('off')
    expect(input().attributes('spellcheck')).toBe('false')
  })

  it('passes what is typed on', async () => {
    const { input, typed } = await open()
    await input().setValue('a-secret-key')
    expect(typed.value).toBe('a-secret-key')
  })

  it('shows and hides what is typed, saying which with the button’s state', async () => {
    const { wrapper, input } = await open()
    const toggle = wrapper.find('[data-test="show-secret"]')
    expect(toggle.attributes('aria-label')).toBe('Show API key')
    expect(toggle.attributes('aria-pressed')).toBe('false')

    await toggle.trigger('click')
    expect(input().attributes('type')).toBe('text')
    expect(toggle.attributes('aria-pressed')).toBe('true')

    await toggle.trigger('click')
    expect(input().attributes('type')).toBe('password')
  })

  it('says when one is saved, and that leaving it empty keeps it', async () => {
    const { wrapper, input } = await open(true)
    expect(input().attributes('placeholder')).toBe('Saved')
    expect(wrapper.text()).toContain('Leave this empty to keep it')
  })

  it('shows its own hint while nothing is saved', async () => {
    const { wrapper, input } = await open(false, 'From System, Access, Users.')
    expect(input().attributes('placeholder')).toBeUndefined()
    expect(wrapper.text()).toContain('From System, Access, Users.')
    expect(wrapper.text()).not.toContain('Leave this empty')
  })
})
