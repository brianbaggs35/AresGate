import type { AiProvider } from '@/api/ai'
import AiProviderPicker from '@/components/AiProviderPicker.vue'
import { ai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(
  props: { providers?: AiProvider[]; asking?: string | null; modelValue?: string | null } = {},
) {
  const mounted = await mountWithPlugins(AiProviderPicker, {
    signedIn: 'admin',
    withApp: true,
    props: { providers: ai().providers, asking: null, modelValue: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const radios = () => mounted.wrapper.findAll('input[type="radio"]')
  const picker = () => mounted.wrapper.findComponent(AiProviderPicker)
  const choices = () => picker().emitted('update:modelValue') ?? []
  return { ...mounted, find, radios, choices }
}

describe('AiProviderPicker', () => {
  it('asks where the AI should run, with a card for each provider in the order given', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.find('legend').text()).toBe('Where should the AI run?')
    expect(find('pick-ollama').text()).toContain('Ollama (on your computer)')
    expect(find('pick-ollama').text()).toContain(
      'Runs models on your own hardware, so nothing leaves your network and nothing is billed.',
    )
    expect(
      wrapper.findAll('label[data-test^="pick-"]').map((card) => card.attributes('data-test')),
    ).toEqual(['pick-ollama', 'pick-ollama_cloud', 'pick-anthropic', 'pick-openai'])
  })

  it('is one group of radio buttons, so the arrow keys move between them', async () => {
    const { radios, wrapper } = await open({ modelValue: 'openai' })

    expect(wrapper.find('fieldset').exists()).toBe(true)
    expect(radios()).toHaveLength(4)
    expect(new Set(radios().map((radio) => radio.attributes('name'))).size).toBe(1)
    expect(radios().map((radio) => (radio.element as HTMLInputElement).checked)).toEqual([
      false,
      false,
      false,
      true,
    ])
  })

  it('marks the one that is chosen', async () => {
    const { find } = await open({ modelValue: 'anthropic' })

    expect(find('pick-anthropic').classes()).toContain('picker__option--chosen')
    expect(find('pick-openai').classes()).not.toContain('picker__option--chosen')
  })

  it('says which provider is in use', async () => {
    const { find, wrapper } = await open({ asking: 'openai' })

    expect(find('pick-openai').find('[data-test="pick-asking"]').text()).toBe('In use')
    expect(wrapper.findAll('[data-test="pick-asking"]')).toHaveLength(1)
  })

  it('chooses the one that is clicked', async () => {
    const { radios, choices } = await open()

    await radios()[2]?.setValue(true)
    await flushPromises()

    expect(choices()).toEqual([['anthropic']])
  })
})
