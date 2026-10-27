import type { ResponseState } from '@/api/incidents'
import ResponseChip from '@/components/ResponseChip.vue'
import { response } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

describe('ResponseChip', () => {
  it.each<[ResponseState, string]>([
    ['banned', 'Banned'],
    ['partly', 'Partly banned'],
    ['ban_ended', 'Ban ended'],
    ['blocked', 'Blocked'],
    ['none', 'No response yet'],
  ])('says %s in words', async (state, label) => {
    const { wrapper } = await mountWithPlugins(ResponseChip, {
      props: { response: response({ state, label }) },
    })

    const chip = wrapper.find('[data-test="incident-response"]')
    expect(chip.text()).toBe(label)
    expect(chip.attributes('data-state')).toBe(state)
  })

  it('says nothing of an incident that names no address', async () => {
    const { wrapper } = await mountWithPlugins(ResponseChip, {
      props: { response: response({ state: 'no_address', label: 'Nothing to block' }) },
    })

    expect(wrapper.find('[data-test="incident-response"]').exists()).toBe(false)
  })
})
