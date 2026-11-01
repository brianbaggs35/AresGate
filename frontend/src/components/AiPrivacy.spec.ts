import AiPrivacy from '@/components/AiPrivacy.vue'
import { anthropic, ollama } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(props: Partial<InstanceType<typeof AiPrivacy>['$props']> = {}) {
  const mounted = await mountWithPlugins(AiPrivacy, {
    signedIn: 'admin',
    withApp: true,
    props: { level: 'balanced', asking: undefined, busy: false, failure: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const input = (level: string) => find(`privacy-${level}`).find('input')
  const changes = () => mounted.wrapper.findComponent(AiPrivacy).emitted('change') ?? []
  return { ...mounted, find, input, changes }
}

describe('AiPrivacy', () => {
  it('offers three levels as one group of radio buttons', async () => {
    const { wrapper, input } = await open()

    expect(wrapper.find('legend').text()).toBe('What may the provider see?')
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(3)
    expect(input('strict').attributes('name')).toBe('ai-redaction')
    expect(input('balanced').element).toHaveProperty('checked', true)
    expect(input('strict').element).toHaveProperty('checked', false)
  })

  it('shows what a provider would read of the same event at each level', async () => {
    const { find } = await open()

    expect(find('privacy-example-strict').text()).toBe(
      'HOST_1 (NAME_2) was probed by EXT_3 on port 22.',
    )
    expect(find('privacy-example-balanced').text()).toBe(
      'HOST_1 (NAME_2) was probed by 203.0.113.5 on port 22.',
    )
    expect(find('privacy-example-local').text()).toContain('192.168.1.20')
  })

  it('says a level was chosen only when it is another one', async () => {
    const { input, changes } = await open()

    await input('balanced').setValue(true)
    await input('strict').setValue(true)
    await flushPromises()

    expect(changes()).toEqual([['strict']])
  })

  it('allows Local for a provider at home, and when none is chosen yet', async () => {
    const none = await open()
    const home = await open({ asking: ollama({ configured: true }) })

    expect(none.input('local').attributes('disabled')).toBeUndefined()
    expect(home.input('local').attributes('disabled')).toBeUndefined()
    expect(home.find('privacy-note').exists()).toBe(false)
  })

  it('does not allow Local for a hosted provider, and says why', async () => {
    const { input, find, changes } = await open({ asking: anthropic({ configured: true }) })

    expect(input('local').attributes('disabled')).toBeDefined()
    expect(find('privacy-note').text()).toContain('Local is for a provider on your own network')
    expect(find('privacy-note').text()).toContain('Anthropic is hosted')
    expect(changes()).toEqual([])
  })

  it('says what is really shown when Local was chosen and the provider has changed since', async () => {
    const { find } = await open({ level: 'local', asking: anthropic({ configured: true }) })

    expect(find('privacy-note').text()).toBe(
      'Anthropic is not on your own network, so it is shown Balanced. Local only applies to a provider that runs at home.',
    )
  })

  it('cannot be changed while a change is being made', async () => {
    const { input } = await open({ busy: true })

    expect(input('strict').attributes('disabled')).toBeDefined()
    expect(input('balanced').attributes('disabled')).toBeDefined()
  })

  it('says why a change was refused', async () => {
    const { find } = await open({ failure: 'Choose strict, balanced or local.' })

    expect(find('privacy-failure').text()).toBe('Choose strict, balanced or local.')
  })
})
