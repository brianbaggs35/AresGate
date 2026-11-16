import * as denialsApi from '@/api/aiDenials'
import { ApiError } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DeniedProposalsCard from '@/components/DeniedProposalsCard.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { denial, denials } from '@/test/aiDenials'

async function open(answer: denialsApi.Denials | Error = denials()) {
  const fetchIt = vi.spyOn(denialsApi, 'fetchDenials')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(DeniedProposalsCard, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (name: string) => mounted.wrapper.find(`[data-test="${name}"]`)
  return { ...mounted, fetchIt, find }
}

describe('DeniedProposalsCard', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(denialsApi, 'fetchDenials').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(DeniedProposalsCard, { signedIn: 'admin' })

    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('says nothing is denied, and for how long a denial stands', async () => {
    const { find } = await open(denials([]))

    expect(find('denials-empty').text()).toContain('Nothing is denied.')
    expect(find('denials-empty').text()).toContain('30 days')
    expect(find('denials-forget-all').exists()).toBe(false)
  })

  it('lists what was denied, in words, with the incident it was for', async () => {
    const { find, wrapper } = await open(
      denials([denial(), denial({ id: 2, kind: 'verdict', value: 'threat', incident_id: 13 })]),
    )

    const rows = wrapper.findAll('li')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.find('[data-test="denial-what"]').text()).toBe('Dismiss')
    expect(rows[0]?.find('[data-test="denial-incident"]').text()).toBe('Scan from 203.0.113.9')
    expect(rows[0]?.text()).toContain('unless the incident changes')
    expect(rows[1]?.find('[data-test="denial-what"]').text()).toBe('Call a real threat')
    expect(find('denials-forget-all').exists()).toBe(true)
  })

  it('says a change it has no words for as it is', async () => {
    const { find } = await open(denials([denial({ value: 'odd' })]))

    expect(find('denial-what').text()).toBe('odd')
  })

  it('forgets one, and lists again', async () => {
    const forget = vi.spyOn(denialsApi, 'forgetDenial').mockResolvedValue(undefined)
    const { find, fetchIt } = await open()
    fetchIt.mockResolvedValue(denials([]))

    await find('denial-forget').trigger('click')
    await flushPromises()

    expect(forget).toHaveBeenCalledWith(1, expect.any(String))
    expect(find('denials-empty').exists()).toBe(true)
  })

  it('says why it could not forget one', async () => {
    vi.spyOn(denialsApi, 'forgetDenial').mockRejectedValue(new ApiError(500, 'Broke.', 'x'))
    const { find } = await open()

    await find('denial-forget').trigger('click')
    await flushPromises()

    expect(find('denials-failure').text()).toBe('Broke.')
    expect(find('denials-list').exists()).toBe(true)
  })

  it('asks before it forgets everything, then does', async () => {
    const forgetAll = vi.spyOn(denialsApi, 'forgetAllDenials').mockResolvedValue({ forgotten: 1 })
    const { find, fetchIt, wrapper } = await open()
    fetchIt.mockResolvedValue(denials([]))

    await find('denials-forget-all').trigger('click')
    await flushPromises()
    expect(forgetAll).not.toHaveBeenCalled()
    wrapper.findComponent(ConfirmDialog).vm.$emit('confirm')
    await flushPromises()

    expect(forgetAll).toHaveBeenCalledOnce()
    expect(find('denials-empty').exists()).toBe(true)
    expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(false)
  })

  it('keeps everything when the question is put away', async () => {
    const forgetAll = vi.spyOn(denialsApi, 'forgetAllDenials')
    const { find, wrapper } = await open()

    await find('denials-forget-all').trigger('click')
    expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(true)
    wrapper.findComponent(ConfirmDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(false)
    expect(forgetAll).not.toHaveBeenCalled()
  })

  it('says why it could not forget everything, and closes the question', async () => {
    vi.spyOn(denialsApi, 'forgetAllDenials').mockRejectedValue(new ApiError(500, 'Broke.', 'x'))
    const { find, wrapper } = await open()

    await find('denials-forget-all').trigger('click')
    wrapper.findComponent(ConfirmDialog).vm.$emit('confirm')
    await flushPromises()

    expect(find('denials-failure').text()).toBe('Broke.')
    expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(false)
  })

  it('says it could not load, and loads again when asked', async () => {
    const { find, fetchIt } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
    expect(find('denials-error').text()).toContain("Can't reach AresGate.")

    fetchIt.mockResolvedValue(denials([]))
    await find('denials-retry').trigger('click')
    await flushPromises()

    expect(find('denials-empty').exists()).toBe(true)
  })
})
