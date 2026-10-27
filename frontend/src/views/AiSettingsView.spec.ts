import * as aiApi from '@/api/ai'
import { ApiError } from '@/api/client'
import AiProviderCard from '@/components/AiProviderCard.vue'
import AiUseCard from '@/components/AiUseCard.vue'
import { ai, anthropic } from '@/test/ai'
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
  const cards = () => mounted.wrapper.findAllComponents(AiProviderCard)
  return { ...mounted, fetchIt, use, find, cards }
}

describe('AiSettingsView', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(aiApi, 'fetchAi').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AiSettingsView, { signedIn: 'admin' })

    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('shows whether AI is used and a card for each provider, in order', async () => {
    const { wrapper, cards } = await open()

    expect(wrapper.findComponent(AiUseCard).exists()).toBe(true)
    expect(cards().map((card) => card.props('provider').key)).toEqual([
      'anthropic',
      'openai',
      'ollama',
      'ollama_cloud',
    ])
    expect(cards()[0]?.props('pricedAsOf')).toBe('2026-10-27')
  })

  it('says so when it cannot be loaded, and loads once it can', async () => {
    const { find, fetchIt, cards } = await open(offline())
    expect(find('ai-error').exists()).toBe(true)
    expect(cards()).toHaveLength(0)

    fetchIt.mockResolvedValue(ai())
    await find('ai-error').find('button').trigger('click')
    await flushPromises()

    expect(cards()).toHaveLength(4)
  })

  it('turns AI on and shows it on', async () => {
    const { wrapper, use, find } = await open(ai({ providers: [READY] }))
    use.mockResolvedValue(ai({ enabled: true, provider: 'anthropic', providers: [READY] }))

    await find('ai-enabled').find('input').setValue(true)
    await flushPromises()

    expect(use).toHaveBeenCalledWith({ enabled: true, provider: 'anthropic' }, 'a-security-token')
    expect(wrapper.findComponent(AiUseCard).props('enabled')).toBe(true)
  })

  it('says why a change was refused, and shows how things really are', async () => {
    const { use, find, fetchIt, wrapper } = await open(ai({ providers: [READY] }))
    use.mockRejectedValue(new ApiError(422, 'Choose which provider to ask.', 'invalid'))
    fetchIt.mockClear()

    await find('ai-enabled').find('input').setValue(true)
    await flushPromises()

    expect(find('ai-use-failure').text()).toBe('Choose which provider to ask.')
    expect(fetchIt).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(AiUseCard).props('enabled')).toBe(false)
  })

  it('shows a provider as it is after it is kept or tested', async () => {
    const { cards } = await open()
    const connected = anthropic({
      configured: true,
      status: 'connected',
      model: 'claude-haiku-5-5',
    })

    cards()[0]?.vm.$emit('changed', connected)
    await flushPromises()

    expect(cards()[0]?.props('provider')).toEqual(connected)
    expect(cards()[1]?.props('provider').key).toBe('openai')
  })

  it('asks how things are after a provider is removed, since AI may have been turned off', async () => {
    const { cards, fetchIt, wrapper } = await open(
      ai({ enabled: true, provider: 'anthropic', providers: [READY] }),
    )
    fetchIt.mockResolvedValue(ai())

    cards()[0]?.vm.$emit('removed', 'anthropic')
    await flushPromises()

    expect(fetchIt).toHaveBeenCalledTimes(2)
    expect(wrapper.findComponent(AiUseCard).props('enabled')).toBe(false)
  })
})
