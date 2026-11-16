import {
  VBtnToggle,
  VCheckbox,
  VRadioGroup,
  VSelect,
  VSlider,
  VTextField,
} from 'vuetify/components'

import * as clearingApi from '@/api/aiClearing'
import { ApiError } from '@/api/client'
import AiClearingCard from '@/components/AiClearingCard.vue'
import { clearing, clearingPreview } from '@/test/aiClearing'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const settle = () => vi.advanceTimersByTimeAsync(0)
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(kept: clearingApi.Clearing | Error = clearing()) {
  const fetchIt = vi.spyOn(clearingApi, 'fetchClearing')
  if (kept instanceof Error) fetchIt.mockRejectedValue(kept)
  else fetchIt.mockResolvedValue(kept)
  const ask = vi.spyOn(clearingApi, 'previewClearing').mockResolvedValue(clearingPreview())
  const save = vi.spyOn(clearingApi, 'saveClearing')
  const mounted = await mountWithPlugins(AiClearingCard, { signedIn: 'admin', withApp: true })
  await flushPromises()
  // From here the pause before the card asks is ours to wait out.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const choose = async (mode: string) => {
    mounted.wrapper.findComponent(VRadioGroup).vm.$emit('update:modelValue', mode)
    await settle()
  }
  const slide = async (to: number) => {
    mounted.wrapper.findComponent(VSlider).vm.$emit('update:modelValue', to)
    await settle()
  }
  const toggle = (label: string) =>
    mounted.wrapper
      .findAllComponents(VBtnToggle)
      .find((item) => item.attributes('data-test') === label)
  const wait = async () => {
    await vi.advanceTimersByTimeAsync(400)
    await settle()
  }
  return { ...mounted, fetchIt, ask, save, find, choose, slide, toggle, wait }
}

describe('AiClearingCard', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a placeholder while it asks, and how to try again when it cannot', async () => {
    vi.spyOn(clearingApi, 'fetchClearing').mockReturnValue(new Promise(() => {}))
    const waiting = await mountWithPlugins(AiClearingCard, { signedIn: 'admin' })
    expect(waiting.wrapper.find('.v-skeleton-loader').exists()).toBe(true)

    const { find, fetchIt } = await open(offline())

    expect(find('clearing-error').text()).toContain("Can't reach AresGate.")
    fetchIt.mockResolvedValue(clearing())
    await find('clearing-error').find('button').trigger('click')
    await settle()
    expect(find('clearing-mode').exists()).toBe(true)
  })

  it('shows how it is kept: suggesting, balanced, nothing named and medium', async () => {
    const { find, wrapper } = await open()

    expect(wrapper.findComponent(VRadioGroup).props('modelValue')).toBe('suggest')
    expect(find('clearing-minimum').text()).toBe('80% sure')
    expect(find('clearing-preset-words').text()).toBe('Clears what it is quite sure of.')
    expect(find('clearing-ceiling-words').text()).toBe(
      'Up to medium. High and critical are left to you.',
    )
    expect(wrapper.findAllComponents(VCheckbox).map((box) => box.props('modelValue'))).toEqual([
      true,
      true,
      true,
    ])
    expect(find('clearing-cap').exists()).toBe(false)
    expect(find('clearing-today').exists()).toBe(false)
  })

  it('hides the terms when it is off', async () => {
    const { find, choose } = await open(clearing({ mode: 'off' }))

    expect(find('clearing-sure').exists()).toBe(false)
    expect(find('clearing-kinds').exists()).toBe(false)

    await choose('suggest')

    expect(find('clearing-sure').exists()).toBe(true)
  })

  it('asks what a change would have cleared once, a moment after the last one', async () => {
    const { ask, slide, wait, find } = await open()

    await slide(70)
    await slide(75)
    await vi.advanceTimersByTimeAsync(399)
    expect(ask).not.toHaveBeenCalled()
    expect(find('clearing-preview').exists()).toBe(false)
    await wait()

    expect(ask).toHaveBeenCalledTimes(1)
    expect(ask).toHaveBeenCalledWith(expect.objectContaining({ minimum: 75 }), 'a-security-token')
    expect(find('clearing-preview').text()).toBe(
      'Of the 12 incidents the AI read in the last 7 days, these settings would have cleared 4.',
    )
    expect(find('clearing-preset-words').text()).toContain('A number of your own.')
  })

  it('says when there is nothing to preview or nothing would have been cleared', async () => {
    const { ask, slide, wait, find } = await open()
    ask.mockResolvedValueOnce(clearingPreview({ read: 0, would_clear: 0 }))
    await slide(70)
    await wait()
    expect(find('clearing-preview').text()).toBe(
      'The AI has not read any incidents in the last 7 days yet.',
    )

    ask.mockResolvedValueOnce(clearingPreview({ read: 1, would_clear: 0 }))
    await slide(71)
    await wait()
    expect(find('clearing-preview').text()).toBe(
      'Of the 1 incident the AI read in the last 7 days, these settings would have cleared none.',
    )
  })

  it('withdraws the question and its answer when the change is undone', async () => {
    const { ask, slide, wait, find } = await open()
    await slide(70)
    await wait()
    expect(find('clearing-preview').exists()).toBe(true)

    await slide(80)
    await settle()

    expect(find('clearing-preview').exists()).toBe(false)
    expect(ask).toHaveBeenCalledTimes(1)
  })

  it('says so when it cannot work out what a change would do, and drops an older answer', async () => {
    const { ask, slide, wait, find } = await open()
    ask.mockRejectedValueOnce(offline())

    await slide(70)
    await wait()

    expect(find('clearing-preview-error').text()).toBe("Can't reach AresGate.")

    let first: (value: clearingApi.ClearingPreview) => void = () => {}
    ask.mockReturnValueOnce(new Promise((resolve) => (first = resolve)))
    await slide(72)
    await wait()
    ask.mockResolvedValueOnce(clearingPreview({ would_clear: 9 }))
    await slide(74)
    await wait()
    first(clearingPreview({ would_clear: 1 }))
    await settle()

    expect(find('clearing-preview').text()).toContain('cleared 9')
  })

  it('drops the failure of an older question too', async () => {
    const { ask, slide, wait, find } = await open()
    let fail: (reason: Error) => void = () => {}
    ask.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    await slide(72)
    await wait()
    ask.mockResolvedValueOnce(clearingPreview({ would_clear: 9 }))
    await slide(74)
    await wait()

    fail(offline())
    await settle()

    expect(find('clearing-preview-error').exists()).toBe(false)
    expect(find('clearing-preview').text()).toContain('cleared 9')
  })

  it('takes a way of being careful as how sure it must be', async () => {
    const { toggle, find } = await open()

    toggle('clearing-presets')?.vm.$emit('update:modelValue', 'careful')
    await settle()
    expect(find('clearing-minimum').text()).toBe('90% sure')

    toggle('clearing-presets')?.vm.$emit('update:modelValue', 'nothing-like-it')
    await settle()
    expect(find('clearing-minimum').text()).toBe('90% sure')
  })

  it('takes the kinds the AI may clear, and says what none means', async () => {
    const { wrapper, find } = await open()
    const boxes = wrapper.findAllComponents(VCheckbox)

    boxes[0]?.vm.$emit('update:modelValue', false)
    await settle()
    boxes[1]?.vm.$emit('update:modelValue', false)
    boxes[2]?.vm.$emit('update:modelValue', false)
    await settle()
    expect(find('clearing-no-kinds').text()).toBe('With none chosen the AI clears nothing.')

    boxes[1]?.vm.$emit('update:modelValue', true)
    await settle()
    expect(find('clearing-no-kinds').exists()).toBe(false)
    expect(wrapper.findAllComponents(VCheckbox).map((box) => box.props('modelValue'))).toEqual([
      false,
      true,
      false,
    ])
  })

  it('takes the programs and how serious', async () => {
    const { wrapper, toggle, find, ask, wait } = await open()

    wrapper.findComponent(VSelect).vm.$emit('update:modelValue', ['wazuh'])
    toggle('clearing-ceilings')?.vm.$emit('update:modelValue', 'high')
    await settle()
    await wait()

    expect(find('clearing-ceiling-words').text()).toBe(
      'Up to high. Critical is always left to you.',
    )
    expect(ask).toHaveBeenCalledWith(
      expect.objectContaining({ sources: ['wazuh'], ceiling: 'high' }),
      'a-security-token',
    )
  })

  it('asks for the most it clears a day only when it clears by itself, and checks it', async () => {
    const { find, wrapper } = await open(clearing({ mode: 'automatic', cleared_today: 3 }))

    expect(find('clearing-today').text()).toBe('Cleared by the AI in the last 24 hours: 3 of 25.')
    const field = wrapper
      .findAllComponents(VTextField)
      .find((item) => item.attributes('data-test') === 'clearing-cap')!
    const rule = (field.props('rules') as ((value: number) => string | true)[])[0]!
    expect(rule(10)).toBe(true)
    for (const value of [-1, 1.5, 501])
      expect(rule(value)).toBe('Use a whole number from 0 to 500.')
  })

  it('takes the most it clears a day as a number', async () => {
    const { find, wait, ask } = await open(clearing({ mode: 'automatic' }))

    await find('clearing-cap').find('input').setValue('7')
    await wait()

    expect(ask).toHaveBeenCalledWith(expect.objectContaining({ daily_cap: 7 }), 'a-security-token')
  })

  it('says why it has stopped, in place of the count', async () => {
    const { find } = await open(
      clearing({
        mode: 'automatic',
        held: 'The AI has stopped clearing. The daily limit is used up.',
      }),
    )

    expect(find('clearing-held').text()).toContain('The AI has stopped clearing.')
    expect(find('clearing-today').exists()).toBe(false)
  })

  it('keeps what was chosen and says so', async () => {
    const { slide, wait, save, find, ask } = await open()
    save.mockResolvedValue(clearing({ minimum: 70, aggressiveness: 'custom' }))

    await slide(70)
    await wait()
    await find('clearing-save').trigger('submit')
    await settle()

    expect(save).toHaveBeenCalledWith(
      {
        mode: 'suggest',
        minimum: 70,
        kinds: ['noise', 'probe', 'unclear'],
        sources: [],
        ceiling: 'medium',
        daily_cap: 25,
      },
      'a-security-token',
    )
    expect(find('clearing-saved').text()).toBe('The settings are saved.')
    expect(find('clearing-preview').exists()).toBe(false)
    expect(ask).toHaveBeenCalledTimes(1)
  })

  it('says what went wrong when it cannot keep them, and keeps what was chosen', async () => {
    const { slide, wait, save, find } = await open()
    save.mockRejectedValue(offline())

    await slide(70)
    await wait()
    await find('clearing-save').trigger('submit')
    await settle()

    expect(find('clearing-failure').text()).toBe("Can't reach AresGate.")
    expect(find('clearing-minimum').text()).toBe('70% sure')
    expect(find('clearing-saved').exists()).toBe(false)
  })

  it('goes back to what is kept', async () => {
    const { slide, wait, find } = await open()
    await slide(70)
    await wait()

    await find('clearing-discard').trigger('click')
    await settle()

    expect(find('clearing-minimum').text()).toBe('80% sure')
    expect(find('clearing-save').attributes('disabled')).toBeDefined()
  })

  it('has nothing to save, or to discard, until something changes', async () => {
    const { find } = await open()

    expect(find('clearing-save').attributes('disabled')).toBeDefined()
    expect(find('clearing-discard').attributes('disabled')).toBeDefined()
  })
})
