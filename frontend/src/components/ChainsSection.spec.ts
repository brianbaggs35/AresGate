import * as threatsApi from '@/api/threats'
import ChainsSection from '@/components/ChainsSection.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { chain } from '@/test/threats'
import { ApiError } from '@/api/client'

async function open(found: threatsApi.ChainPage | Error) {
  const fetchIt = vi.spyOn(threatsApi, 'fetchChains')
  if (found instanceof Error) fetchIt.mockRejectedValue(found)
  else fetchIt.mockResolvedValue(found)
  const mounted = await mountWithPlugins(ChainsSection, { signedIn: 'admin', withApp: true })
  await flushPromises()
  return { ...mounted, fetchIt }
}

describe('ChainsSection', () => {
  it('lists the attacks across two devices, the most recent six', async () => {
    const { wrapper, fetchIt } = await open({
      total: 7,
      items: [chain({ id: 1 }), chain({ id: 2 })],
    })

    expect(fetchIt).toHaveBeenCalledWith({ limit: 6 })
    expect(wrapper.findAll('[data-test="chain-card"]')).toHaveLength(2)
    expect(wrapper.find('[data-test="chains-count"]').text()).toContain('7 attacks')
  })

  it('says one attack in the singular', async () => {
    const { wrapper } = await open({ total: 1, items: [chain()] })

    expect(wrapper.find('[data-test="chains-count"]').text()).toContain('1 attack that got into')
  })

  it('draws nothing while there are none', async () => {
    const { wrapper } = await open({ total: 0, items: [] })

    expect(wrapper.find('[data-test="chains"]').exists()).toBe(false)
  })

  it('draws nothing, and no error, when it could not read them', async () => {
    const { wrapper } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))

    expect(wrapper.find('[data-test="chains"]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
