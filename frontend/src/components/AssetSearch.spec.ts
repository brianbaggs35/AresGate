import { mountWithPlugins } from '@/test/mount'
import AssetSearch from '@/components/AssetSearch.vue'

async function open(text = '') {
  const mounted = await mountWithPlugins(AssetSearch, { props: { modelValue: text } })
  const input = () => mounted.wrapper.find('input').element
  const type = async (value: string) => {
    await mounted.wrapper.find('input').setValue(value)
  }
  return { ...mounted, input, type }
}

describe('AssetSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the search that is applied', async () => {
    const { input } = await open('laptop')

    expect(input().value).toBe('laptop')
  })

  it('applies what is typed after a pause, not letter by letter', async () => {
    const { wrapper, type } = await open()

    await type('lap')
    await type('laptop')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    vi.advanceTimersByTime(400)

    expect(wrapper.emitted('update:modelValue')).toEqual([['laptop']])
  })

  it('applies it at once with Enter, without its spaces', async () => {
    const { wrapper, type } = await open()

    await type('  laptop ')
    await wrapper.find('input').trigger('keydown.enter')

    expect(wrapper.emitted('update:modelValue')).toEqual([['laptop']])
    vi.advanceTimersByTime(400)
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
  })

  it('says nothing about a search that is the one applied already', async () => {
    const { wrapper } = await open('laptop')

    await wrapper.find('input').trigger('keydown.enter')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('clears the search with the button', async () => {
    const { wrapper } = await open('laptop')

    await wrapper.find('.v-field__clearable .v-icon').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['']])
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
  })

  it('shows a search that comes from outside, and keeps the one just typed', async () => {
    const { wrapper, type, input } = await open('laptop')

    await wrapper.setProps({ modelValue: '' })
    expect(input().value).toBe('')

    await type('phone')
    await wrapper.setProps({ modelValue: 'phone' })
    expect(input().value).toBe('phone')
  })

  it('takes a typed search back when the page changes it', async () => {
    const { wrapper, type, input } = await open('laptop')
    await type('half typed')

    await wrapper.setProps({ modelValue: 'camera' })

    expect(input().value).toBe('camera')
  })

  it('can be given the focus', async () => {
    const { wrapper } = await open()

    ;(wrapper.vm as unknown as { focus: () => void }).focus()

    expect(document.activeElement).toBe(wrapper.find('input').element)
  })

  it('does not apply a search after it has gone', async () => {
    const { wrapper, type } = await open()
    await type('laptop')

    wrapper.unmount()
    vi.advanceTimersByTime(400)

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
