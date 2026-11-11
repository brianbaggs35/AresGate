import { ApiError } from '@/api/client'
import * as threatsApi from '@/api/threats'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { chainDetail, chainStep } from '@/test/threats'
import ChainView from '@/views/ChainView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(found: threatsApi.ChainDetail | Error = chainDetail()) {
  const fetchIt = vi.spyOn(threatsApi, 'fetchChain')
  if (found instanceof Error) fetchIt.mockRejectedValue(found)
  else fetchIt.mockResolvedValue(found)
  const mounted = await mountWithPlugins(ChainView, {
    signedIn: 'admin',
    withApp: true,
    route: '/threats/chains/4',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetchIt, find }
}

describe('ChainView', () => {
  it('asks for the chain that is in the address of the page', async () => {
    const { fetchIt } = await open()

    expect(fetchIt).toHaveBeenCalledWith(4)
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(threatsApi, 'fetchChain').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(ChainView, {
      signedIn: 'admin',
      route: '/threats/chains/4',
    })

    expect(wrapper.find('[data-test="chain-loading"]').exists()).toBe(true)
  })

  it('names the device, says what happened and leads back to the threats', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.find('h1').text()).toBe('Attack on Kitchen camera (192.168.1.20)')
    expect(wrapper.text()).toContain('93.184.216.34 attacked 192.168.1.20')
    expect(find('back').attributes('href')).toBe('/threats')
  })

  it('says a chain that was seen is seen, and draws its steps', async () => {
    const { wrapper, find } = await open()

    expect(find('chain-certainty').text()).toContain('Seen, not guessed')
    expect(wrapper.findAll('[data-test="path-step"]')).toHaveLength(2)
  })

  it('says part of a chain that was not seen is inferred', async () => {
    const { find } = await open(
      chainDetail({
        confirmed: false,
        path: [chainStep(), chainStep({ role: 'callout', link: 'inferred', incident_id: 12 })],
      }),
    )

    expect(find('chain-certainty').text()).toContain('Part of this is inferred')
  })

  it('says why it is a threat, and leaves that out when nothing says', async () => {
    const shown = await open()
    const none = await open(chainDetail({ why: [] }))

    expect(shown.find('why').text()).toContain('more than scanning')
    expect(none.find('why-card').exists()).toBe(false)
  })

  it('says so when it could not be read, and asks again', async () => {
    const { find, fetchIt } = await open(offline())

    expect(find('chain-error').text()).toContain("Can't reach AresGate.")
    fetchIt.mockResolvedValue(chainDetail())
    await find('chain-error').find('button').trigger('click')
    await flushPromises()

    expect(find('chain-error').exists()).toBe(false)
  })

  it('says a chain that is gone is gone, and offers no retry', async () => {
    const { find } = await open(new ApiError(404, "There's no such chain.", 'not-found'))

    expect(find('chain-error').text()).toContain('It may have been removed.')
    expect(find('chain-error').find('button').exists()).toBe(false)
  })

  it('keeps what it has while a refresh fails, says so, and recovers', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { find, fetchIt, wrapper } = await open()
      fetchIt.mockRejectedValue(offline())

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(find('chain-stale').text()).toContain("Can't reach AresGate.")
      expect(wrapper.findAll('[data-test="path-step"]')).toHaveLength(2)

      fetchIt.mockResolvedValue(chainDetail())
      vi.advanceTimersByTime(30_000)
      await flushPromises()
      expect(find('chain-stale').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('drops the answer of a request that a newer one has taken the place of', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { find, fetchIt } = await open()
      let late: (found: threatsApi.ChainDetail) => void = () => {}
      fetchIt.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchIt.mockResolvedValueOnce(chainDetail({ device_name: 'Newer name' }))

      vi.advanceTimersByTime(60_000)
      await flushPromises()
      late(chainDetail({ device_name: 'Older name' }))
      await flushPromises()

      expect(find('page-heading').text()).toContain('Newer name')
    } finally {
      vi.useRealTimers()
    }
  })

  it('drops the failure of a request that a newer one has taken the place of', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { find, fetchIt } = await open()
      let late: (reason: Error) => void = () => {}
      fetchIt.mockReturnValueOnce(new Promise((_, reject) => (late = reject)))
      fetchIt.mockResolvedValueOnce(chainDetail())

      vi.advanceTimersByTime(60_000)
      await flushPromises()
      late(offline())
      await flushPromises()

      expect(find('chain-stale').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
