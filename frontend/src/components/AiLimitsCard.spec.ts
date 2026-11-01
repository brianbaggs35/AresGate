import * as usageApi from '@/api/aiUsage'
import { ApiError } from '@/api/client'
import AiLimitsCard from '@/components/AiLimitsCard.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { limit } from '@/test/aiUsage'

const NOT_SET = [limit(), limit({ period: 'month', spent_micros: 82_000 })]
const SET = [
  limit({ limit_micros: 2_000_000, spent_micros: 1_700_000, state: 'warning' }),
  limit({ period: 'month', limit_micros: 50_000_000, spent_micros: 82_000, state: 'ok' }),
]

async function show(limits = NOT_SET) {
  const save = vi.spyOn(usageApi, 'saveLimits')
  const mounted = await mountWithPlugins(AiLimitsCard, {
    signedIn: 'admin',
    props: { limits },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const type = async (field: string, text: string) => {
    await find(field).find('input').setValue(text)
    await flushPromises()
  }
  const emitted = () => mounted.wrapper.emitted('changed')
  return { ...mounted, save, find, type, emitted }
}

describe('AiLimitsCard', () => {
  it('shows what has been spent when there is no limit, with no meter', async () => {
    const { find } = await show()

    expect(find('limit-day-words').text()).toBe('$0.01 spent, with no limit')
    expect(find('limit-day-meter').exists()).toBe(false)
    expect(find('limit-daily-field').find('input').element.value).toBe('')
  })

  it('shows how much of a limit is gone, and keeps the limits in the fields', async () => {
    const { find } = await show(SET)

    expect(find('limit-day-words').text()).toBe('$1.70 of $2.00: nearly used up')
    expect(find('limit-day-meter').attributes('aria-label')).toBe('Daily limit: 85 percent spent')
    expect(find('limit-month-words').text()).toBe('$0.08 of $50.00')
    expect(find('limit-daily-field').find('input').element.value).toBe('2')
    expect(find('limit-monthly-field').find('input').element.value).toBe('50')
  })

  it('keeps the limits that were typed, and tells the page', async () => {
    const { find, type, save, emitted } = await show()
    save.mockResolvedValue(SET)

    await type('limit-daily-field', ' 2.50 ')
    await type('limit-monthly-field', '')
    await find('limits-save').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith({ daily: '2.50', monthly: null }, 'a-security-token')
    expect(emitted()?.[0]).toEqual([SET])
    expect(find('limits-saved').text()).toBe('The limits are saved.')
  })

  it('follows the limits when the page asks again', async () => {
    const { find, wrapper } = await show()

    await wrapper.setProps({ limits: SET })

    expect(find('limit-daily-field').find('input').element.value).toBe('2')
  })

  it.each(['abc', '0', '1.234', '-1', '12345678'])('refuses %s', async (text) => {
    const { find, type, save } = await show()

    await type('limit-daily-field', text)

    expect(find('limits-save').attributes('disabled')).toBeDefined()
    expect(save).not.toHaveBeenCalled()
  })

  it.each(['', '5', '2.50', '0.5'])('accepts %s', async (text) => {
    const { find, type } = await show()

    await type('limit-monthly-field', text)

    expect(find('limits-save').attributes('disabled')).toBeUndefined()
  })

  it('explains why an amount is refused', async () => {
    const { wrapper, type } = await show()

    await type('limit-daily-field', 'abc')
    expect(wrapper.text()).toContain('Use dollars and cents, such as 5 or 2.50.')

    await type('limit-daily-field', '0')
    expect(wrapper.text()).toContain('Use more than nothing, or leave it empty for no limit.')
  })

  it('says so when the limits could not be kept', async () => {
    const { find, save, emitted } = await show()
    save.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))

    await find('limits-save').trigger('click')
    await flushPromises()

    expect(find('limits-failure').text()).toBe("Can't reach AresGate.")
    expect(find('limits-saved').exists()).toBe(false)
    expect(emitted()).toBeUndefined()
  })
})
