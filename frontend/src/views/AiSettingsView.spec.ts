import * as aiApi from '@/api/ai'
import { ApiError } from '@/api/client'
import AiProviderForm from '@/components/AiProviderForm.vue'
import AiProviderPicker from '@/components/AiProviderPicker.vue'
import AiUseSwitch from '@/components/AiUseSwitch.vue'
import { ai, anthropic, ollama, openai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AiSettingsView from '@/views/AiSettingsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

const READY = anthropic({
  configured: true,
  key_saved: true,
  model: 'claude-haiku-5-5',
  status: 'connected',
})

async function open(answer: aiApi.Ai | Error = ai()) {
  const fetchIt = vi.spyOn(aiApi, 'fetchAi')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const use = vi.spyOn(aiApi, 'useAi')
  const mounted = await mountWithPlugins(AiSettingsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const forms = () => mounted.wrapper.findAllComponents(AiProviderForm)
  const pick = async (key: string) => {
    await find(`pick-${key}`).find('input').setValue(true)
    await flushPromises()
  }
  return { ...mounted, fetchIt, use, find, forms, pick }
}

describe('AiSettingsView', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(aiApi, 'fetchAi').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AiSettingsView, { signedIn: 'admin' })

    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('is one card that says AI is optional, and offers the providers to choose from', async () => {
    const { wrapper, find } = await open()

    expect(find('ai-card').find('h2').text()).toBe('AI provider')
    expect(find('ai-card').text()).toContain("It's optional.")
    expect(wrapper.findComponent(AiProviderPicker).props('providers')).toHaveLength(4)
  })

  it('shows the settings of none until a provider is chosen, when none is set up', async () => {
    const { forms, find } = await open()

    expect(forms()).toHaveLength(0)
    expect(find('ai-state').text()).toBe('Off')
    expect(find('ai-choose').text()).toContain('Choose one to set it up.')
  })

  it('shows only the settings of the provider that was chosen', async () => {
    const { forms, pick, find } = await open()

    await pick('openai')

    expect(forms()).toHaveLength(1)
    expect(find('ai-choose').exists()).toBe(false)
    expect(forms()[0]?.props('provider').key).toBe('openai')
    expect(forms()[0]?.props('pricedAsOf')).toBe('2026-10-27')
    expect(forms()[0]?.props('freeModelsAsOf')).toBe('2026-10-27')

    await pick('ollama')

    expect(forms()[0]?.props('provider').key).toBe('ollama')
  })

  it('starts on the provider that is asked, and says AI is on with its model', async () => {
    const { forms, find, wrapper } = await open(
      ai({
        enabled: true,
        provider: 'anthropic',
        providers: [ollama(), READY, openai()],
      }),
    )

    expect(forms()[0]?.props('provider').key).toBe('anthropic')
    expect(find('ai-state').text()).toBe('On · Claude Haiku 5.5')
    expect(wrapper.findComponent(AiProviderPicker).props('asking')).toBe('anthropic')
  })

  it('starts on a provider that is set up when none is asked', async () => {
    const { forms, wrapper } = await open(ai({ providers: [ollama(), READY, openai()] }))

    expect(forms()[0]?.props('provider').key).toBe('anthropic')
    expect(wrapper.findComponent(AiProviderPicker).props('asking')).toBeNull()
  })

  it('keeps what was typed for a provider while another is looked at', async () => {
    const { find, pick, forms } = await open()
    await pick('anthropic')
    await find('provider-key').find('input').setValue('sk-typed')

    await pick('openai')
    await pick('anthropic')

    expect(forms()[0]?.props('provider').key).toBe('anthropic')
    expect((find('provider-key').find('input').element as HTMLInputElement).value).toBe('sk-typed')
  })

  it('says so when it cannot be loaded, and loads once it can', async () => {
    const { find, fetchIt, wrapper } = await open(offline())
    expect(find('ai-error').exists()).toBe(true)
    expect(wrapper.findComponent(AiProviderPicker).exists()).toBe(false)

    fetchIt.mockResolvedValue(ai())
    await find('ai-error').find('button').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(AiProviderPicker).exists()).toBe(true)
  })

  it('turns AI on for the provider that is shown, and says so', async () => {
    const { use, find } = await open(ai({ providers: [ollama(), READY] }))
    use.mockResolvedValue(
      ai({ enabled: true, provider: 'anthropic', providers: [ollama(), READY] }),
    )

    await find('ai-enabled').find('input').setValue(true)
    await flushPromises()

    expect(use).toHaveBeenCalledWith({ enabled: true, provider: 'anthropic' }, 'a-security-token')
    expect(find('ai-state').text()).toBe('On · Claude Haiku 5.5')
  })

  it('says why a change was refused, and shows how things really are', async () => {
    const { use, find, fetchIt, wrapper } = await open(ai({ providers: [ollama(), READY] }))
    use.mockRejectedValue(new ApiError(422, 'Choose which provider to ask.', 'invalid'))
    fetchIt.mockClear()

    await find('ai-enabled').find('input').setValue(true)
    await flushPromises()

    expect(find('ai-use-failure').text()).toBe('Choose which provider to ask.')
    expect(fetchIt).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(AiUseSwitch).props('enabled')).toBe(false)
  })

  it('shows a provider as it is after it is kept or tested', async () => {
    const { forms, pick } = await open()
    await pick('anthropic')
    const connected = anthropic({
      configured: true,
      status: 'connected',
      model: 'claude-haiku-5-5',
    })

    forms()[0]?.vm.$emit('changed', connected)
    await flushPromises()

    expect(forms()[0]?.props('provider')).toEqual(connected)
  })

  it('asks how things are after a provider is removed, since AI may have been turned off', async () => {
    const { forms, fetchIt, find } = await open(
      ai({ enabled: true, provider: 'anthropic', providers: [ollama(), READY] }),
    )
    fetchIt.mockResolvedValue(ai())

    forms()[0]?.vm.$emit('removed', 'anthropic')
    await flushPromises()

    expect(fetchIt).toHaveBeenCalledTimes(2)
    expect(find('ai-state').text()).toBe('Off')
  })
})
