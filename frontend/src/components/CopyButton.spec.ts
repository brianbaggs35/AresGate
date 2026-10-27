import CopyButton from '@/components/CopyButton.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

function open() {
  return mountWithPlugins(CopyButton, {
    withApp: true,
    props: { text: '93.184.216.34', label: 'From' },
  })
}

function clipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
}

afterEach(() => {
  vi.useRealTimers()
  Reflect.deleteProperty(navigator, 'clipboard')
})

describe('CopyButton', () => {
  it('is named for what it copies', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('button').attributes('aria-label')).toBe('Copy From')
    expect(wrapper.find('output').text()).toBe('')
  })

  it('puts the text on the clipboard and says so, then goes back to what it was', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue()
    clipboard(writeText)
    const { wrapper } = await open()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

    await wrapper.find('button').trigger('click')
    await vi.advanceTimersByTimeAsync(0)

    expect(writeText).toHaveBeenCalledWith('93.184.216.34')
    expect(wrapper.find('output').text()).toBe('Copied')
    expect(wrapper.find('button').classes()).toContain('text-success')

    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.find('output').text()).toBe('')
  })

  it('says so when the browser would not let it', async () => {
    clipboard(vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('no')))
    const { wrapper } = await open()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('output').text()).toBe("Couldn't copy")
    expect(wrapper.find('button').classes()).toContain('text-error')
  })

  it('says so when there is no clipboard at all', async () => {
    const { wrapper } = await open()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('output').text()).toBe("Couldn't copy")
  })

  it('does not change anything after it has gone', async () => {
    clipboard(vi.fn<(text: string) => Promise<void>>().mockResolvedValue())
    const { wrapper } = await open()
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    await wrapper.find('button').trigger('click')
    await vi.advanceTimersByTimeAsync(0)

    wrapper.unmount()

    expect(vi.getTimerCount()).toBe(0)
  })
})
