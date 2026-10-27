import { VSelect } from 'vuetify/components'

import AiUseCard from '@/components/AiUseCard.vue'
import { anthropic, ollama, openai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const READY = anthropic({
  configured: true,
  key_saved: true,
  model: 'claude-haiku-5-5',
  status: 'connected',
})
const OTHER = openai({ configured: true, key_saved: true, model: 'gpt-6-luna' })

async function open(props: Partial<InstanceType<typeof AiUseCard>['$props']> = {}) {
  const mounted = await mountWithPlugins(AiUseCard, {
    signedIn: 'admin',
    withApp: true,
    props: {
      enabled: false,
      provider: null,
      providers: [anthropic(), openai(), ollama()],
      busy: false,
      failure: null,
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const card = () => mounted.wrapper.findComponent(AiUseCard)
  const changes = () => card().emitted('change') ?? []
  const toggle = async (on: boolean) => {
    await find('ai-enabled').find('input').setValue(on)
    await flushPromises()
  }
  const choose = async (provider: string | null) => {
    mounted.wrapper.findComponent(VSelect).vm.$emit('update:modelValue', provider)
    await flushPromises()
  }
  return { ...mounted, find, changes, toggle, choose }
}

describe('AiUseCard', () => {
  it('says what AI is for, and that it only gives opinions', async () => {
    const { find } = await open()

    expect(find('section-description').text()).toContain('it never acts on its own')
    expect(find('section-description').text()).toContain('everything works without it')
  })

  it('cannot be turned on until a provider is ready, and says what a provider needs', async () => {
    const { find } = await open()

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
    expect(find('ai-provider').attributes('class')).toContain('v-input--disabled')
    expect(find('ai-use-hint').text()).toContain('Set up a provider below first')
  })

  it('does not count a provider that has no model or no key', async () => {
    const { find } = await open({
      providers: [
        anthropic({ configured: true, key_saved: false, model: 'claude-haiku-5-5' }),
        ollama({ configured: true, model: '' }),
      ],
    })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
  })

  it('turns on with the only provider that is ready', async () => {
    const { toggle, changes } = await open({ providers: [READY, openai()] })

    await toggle(true)

    expect(changes()).toEqual([[{ enabled: true, provider: 'anthropic' }]])
  })

  it('stops saying a provider is needed once one is ready', async () => {
    const { find } = await open({ providers: [READY] })

    expect(find('ai-use-hint').exists()).toBe(false)
  })

  it('turns on with the provider that is asked, when one is', async () => {
    const { toggle, changes } = await open({ providers: [READY, OTHER], provider: 'openai' })

    await toggle(true)

    expect(changes()).toEqual([[{ enabled: true, provider: 'openai' }]])
  })

  it('turns on with none chosen when more than one is ready, and the page says to choose', async () => {
    const { toggle, changes } = await open({ providers: [READY, OTHER] })

    await toggle(true)

    expect(changes()).toEqual([[{ enabled: true, provider: null }]])
  })

  it('turns off, keeping the provider chosen', async () => {
    const { toggle, changes } = await open({
      providers: [READY],
      enabled: true,
      provider: 'anthropic',
    })

    await toggle(false)

    expect(changes()).toEqual([[{ enabled: false, provider: 'anthropic' }]])
  })

  it('turns off with none chosen', async () => {
    const { toggle, changes } = await open({ providers: [READY], enabled: true })

    await toggle(false)

    expect(changes()).toEqual([[{ enabled: false, provider: null }]])
  })

  it('lists the providers that are ready, each with its model', async () => {
    const { wrapper } = await open({ providers: [READY, OTHER, anthropic()] })

    const items = wrapper.findComponent(VSelect).props('items') as unknown[]

    expect(items).toEqual([
      { value: 'anthropic', title: 'Anthropic', props: { subtitle: 'claude-haiku-5-5' } },
      { value: 'openai', title: 'OpenAI', props: { subtitle: 'gpt-6-luna' } },
    ])
  })

  it('changes which provider is asked, keeping AI on or off', async () => {
    const { choose, changes } = await open({
      providers: [READY, OTHER],
      enabled: true,
      provider: 'anthropic',
    })

    await choose('openai')
    await choose(null)

    expect(changes()).toEqual([
      [{ enabled: true, provider: 'openai' }],
      [{ enabled: true, provider: null }],
    ])
  })

  it('shows why the last change was refused', async () => {
    const { find } = await open({ failure: 'Choose which provider to ask.' })

    expect(find('ai-use-failure').text()).toBe('Choose which provider to ask.')
  })

  it('cannot be changed while a change is under way', async () => {
    const { find } = await open({ providers: [READY], busy: true })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
  })

  it('lets AI be turned off even when no provider is ready any more', async () => {
    const { find } = await open({ providers: [], enabled: true })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeUndefined()
  })
})
