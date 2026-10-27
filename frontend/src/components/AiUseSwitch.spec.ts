import AiUseSwitch from '@/components/AiUseSwitch.vue'
import { anthropic, ollama, openai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const READY = anthropic({
  configured: true,
  key_saved: true,
  model: 'claude-haiku-5-5',
  status: 'connected',
})
const OTHER = openai({ configured: true, key_saved: true, model: 'gpt-6-luna' })

async function open(props: Partial<InstanceType<typeof AiUseSwitch>['$props']> = {}) {
  const mounted = await mountWithPlugins(AiUseSwitch, {
    signedIn: 'admin',
    withApp: true,
    props: {
      provider: READY,
      enabled: false,
      asking: undefined,
      busy: false,
      failure: null,
      ...props,
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const changes = () => mounted.wrapper.findComponent(AiUseSwitch).emitted('change') ?? []
  const toggle = async (on: boolean) => {
    await find('ai-enabled').find('input').setValue(on)
    await flushPromises()
  }
  const checked = () => (find('ai-enabled').find('input').element as HTMLInputElement).checked
  return { ...mounted, find, changes, toggle, checked }
}

describe('AiUseSwitch', () => {
  it('says what it is for, and that AI only gives opinions', async () => {
    const { find } = await open()

    expect(find('ai-enabled').text()).toBe('Use AI with Anthropic')
    expect(find('ai-use-hint').text()).toContain('it never acts on its own')
    expect(find('ai-use-hint').text()).toContain('everything works without it')
  })

  it('cannot be turned on until the provider is set up, and says what it needs', async () => {
    const { find } = await open({ provider: anthropic() })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
    expect(find('ai-use-hint').text()).toBe(
      'Save Anthropic first: it needs a model and, if it takes one, an API key.',
    )
  })

  it('does not count a provider that has no model or no key', async () => {
    const noKey = await open({
      provider: anthropic({ configured: true, key_saved: false, model: 'claude-haiku-5-5' }),
    })
    const noModel = await open({ provider: ollama({ configured: true, model: '' }) })

    expect(noKey.find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
    expect(noModel.find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
  })

  it('turns AI on with the provider that is shown', async () => {
    const { toggle, changes } = await open()

    await toggle(true)

    expect(changes()).toEqual([[{ enabled: true, provider: 'anthropic' }]])
  })

  it('shows it on for the provider that is asked', async () => {
    const { checked } = await open({ enabled: true, asking: READY })

    expect(checked()).toBe(true)
  })

  it('turns off, keeping the provider that is asked', async () => {
    const { toggle, changes } = await open({ enabled: true, asking: READY })

    await toggle(false)

    expect(changes()).toEqual([[{ enabled: false, provider: 'anthropic' }]])
  })

  it('says AI is on with another provider, and that turning it on here moves it', async () => {
    const { find, checked, toggle, changes } = await open({
      provider: READY,
      enabled: true,
      asking: OTHER,
    })

    expect(checked()).toBe(false)
    expect(find('ai-use-hint').text()).toBe(
      'AI is on with OpenAI. Turning this on asks Anthropic instead.',
    )
    await toggle(true)
    expect(changes()).toEqual([[{ enabled: true, provider: 'anthropic' }]])
  })

  it('says nothing of another provider when AI is off', async () => {
    const { find } = await open({ enabled: false, asking: OTHER })

    expect(find('ai-use-hint').text()).not.toContain('AI is on with')
  })

  it('shows why the last change was refused', async () => {
    const { find } = await open({ failure: 'Choose which provider to ask.' })

    expect(find('ai-use-failure').text()).toBe('Choose which provider to ask.')
  })

  it('cannot be changed while a change is under way', async () => {
    const { find } = await open({ busy: true })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeDefined()
  })

  it('lets AI be turned off even when the provider is no longer set up', async () => {
    const { find } = await open({
      provider: anthropic(),
      enabled: true,
      asking: anthropic({ key_saved: true, configured: true, model: 'claude-haiku-5-5' }),
    })

    expect(find('ai-enabled').find('input').attributes('disabled')).toBeUndefined()
  })
})
