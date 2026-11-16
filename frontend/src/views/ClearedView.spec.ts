import * as clearedApi from '@/api/aiCleared'
import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import { clearedItem, clearedPage } from '@/test/cleared'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'
import ClearedView from '@/views/ClearedView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const changed = (done = 1, skipped = 0): clearedApi.ClearedChanged => ({
  done,
  skipped,
  counts: { waiting: 0, cleared: 0 },
})

async function open(first: clearedApi.ClearedPage | Error = clearedPage(), path = '/cleared') {
  const fetchIt = vi.spyOn(clearedApi, 'fetchCleared')
  if (first instanceof Error) fetchIt.mockRejectedValue(first)
  else fetchIt.mockResolvedValue(first)
  const confirm = vi.spyOn(clearedApi, 'confirmCleared').mockResolvedValue(changed())
  const takeBack = vi.spyOn(clearedApi, 'takeBackCleared').mockResolvedValue(changed())
  const change = vi.spyOn(verdictsApi, 'changeVerdict').mockResolvedValue(given())
  const mounted = await mountWithPlugins(ClearedView, {
    signedIn: 'admin',
    withApp: true,
    route: path,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const cards = () => mounted.wrapper.findAll('[data-test="cleared-card"]')
  return { ...mounted, fetchIt, confirm, takeBack, change, find, cards }
}

const two = (kind: clearedApi.ClearedState = 'waiting') =>
  clearedPage({
    state: kind,
    total: 2,
    items: [clearedItem({ kind, id: 4 }), clearedItem({ kind, id: 5, verdict: 'low_priority' })],
    counts: { waiting: 2, cleared: 2 },
  })

describe('ClearedView', () => {
  it('shows a placeholder while it asks, and says when it could not', async () => {
    vi.spyOn(clearedApi, 'fetchCleared').mockReturnValue(new Promise(() => {}))
    const loading = await mountWithPlugins(ClearedView, { signedIn: 'admin' })
    expect(loading.wrapper.find('[data-test="cleared-loading"]').exists()).toBe(true)

    const failed = await open(offline())
    expect(failed.find('cleared-error').text()).toContain("Can't reach AresGate.")
  })

  it('tries again from the error', async () => {
    const { find, fetchIt, cards } = await open(offline())
    fetchIt.mockResolvedValue(clearedPage())

    await find('retry').trigger('click')
    await flushPromises()

    expect(find('cleared-error').exists()).toBe(false)
    expect(cards()).toHaveLength(1)
  })

  it('lists what waits, with how many are in each list', async () => {
    const { cards, find, wrapper } = await open()

    expect(cards()).toHaveLength(1)
    expect(wrapper.find('[data-test="cleared-list-waiting"]').text()).toBe('Waiting for you 1')
    expect(wrapper.find('[data-test="cleared-list-cleared"]').text()).toBe('Cleared by the AI 2')
    expect(find('cleared-settings').attributes('href')).toBe('/settings/ai')
    expect(find('cleared-off').exists()).toBe(false)
    expect(find('cleared-held').exists()).toBe(false)
  })

  it('starts on what the AI cleared when asked to', async () => {
    const { fetchIt } = await open(clearedPage({ state: 'cleared' }), '/cleared?state=cleared')

    expect(fetchIt).toHaveBeenCalledWith('cleared', 20)
  })

  it('says when the AI is off, or is held back', async () => {
    const off = await open(clearedPage({ mode: 'off' }))
    expect(off.find('cleared-off').text()).toContain('switched off')

    const held = await open(clearedPage({ held: 'The AI has stopped clearing.' }))
    expect(held.find('cleared-held').text()).toBe('The AI has stopped clearing.')
  })

  it('says what each list holds when empty', async () => {
    const { find, fetchIt, wrapper } = await open(clearedPage({ total: 0, items: [] }))
    expect(find('cleared-empty').text()).toContain('Nothing is waiting')
    expect(find('cleared-bulk').exists()).toBe(false)

    fetchIt.mockResolvedValue(clearedPage({ state: 'cleared', total: 0, items: [] }))
    await wrapper.find('[data-test="cleared-list-cleared"]').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith('cleared', 20)
    expect(find('cleared-empty').text()).toContain('Nothing to confirm')
  })

  it('asks again every minute, keeping what it shows', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { fetchIt, cards } = await open()
      fetchIt.mockClear()

      vi.advanceTimersByTime(60_000)
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledWith('waiting', 20)
      expect(cards()).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('drops the answer to a question that was asked before another', async () => {
    const { fetchIt, wrapper, cards } = await open()
    let late: (page: clearedApi.ClearedPage) => void = () => {}
    fetchIt.mockReturnValueOnce(
      new Promise((resolve) => {
        late = resolve
      }),
    )
    fetchIt.mockResolvedValue(clearedPage({ state: 'cleared', total: 0, items: [] }))

    wrapper.findComponent({ name: 'ClearedCard' }).vm.$emit('confirm')
    await flushPromises()
    await wrapper.find('[data-test="cleared-list-cleared"]').trigger('click')
    await flushPromises()
    late(two())
    await flushPromises()

    expect(cards()).toHaveLength(0)
  })

  it('drops the failure of a question that was asked before another', async () => {
    const { fetchIt, wrapper, find } = await open()
    let late: (error: Error) => void = () => {}
    fetchIt.mockReturnValueOnce(
      new Promise((_, reject) => {
        late = reject
      }),
    )
    fetchIt.mockResolvedValue(clearedPage({ state: 'cleared', total: 0, items: [] }))

    wrapper.findComponent({ name: 'ClearedCard' }).vm.$emit('confirm')
    await flushPromises()
    await wrapper.find('[data-test="cleared-list-cleared"]').trigger('click')
    await flushPromises()
    late(offline())
    await flushPromises()

    expect(find('cleared-stale').exists()).toBe(false)
  })

  it('keeps what it shows, and says so, when asking again fails', async () => {
    const { fetchIt, find, cards } = await open()
    fetchIt.mockRejectedValue(offline())

    await cards()[0]?.find('[data-test="cleared-confirm"]').trigger('click')
    await flushPromises()

    expect(find('cleared-stale').text()).toContain('What is shown is from earlier.')
    expect(cards()).toHaveLength(1)
  })

  it('confirms one, and says so', async () => {
    const { cards, confirm, find, fetchIt } = await open(two())
    fetchIt.mockResolvedValue(clearedPage({ total: 1, items: [clearedItem({ id: 5 })] }))

    await cards()[0]?.find('[data-test="cleared-confirm"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      [{ kind: 'waiting', id: 4 }],
      'a-security-token',
      undefined,
    )
    expect(find('cleared-notice').text()).toBe('You confirmed 1 incident.')
    expect(cards()).toHaveLength(1)
  })

  it('gives a suggestion as the other verdict', async () => {
    const { cards, confirm } = await open(two())

    await cards()[0]?.find('[data-test="cleared-other"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      [{ kind: 'waiting', id: 4 }],
      'a-security-token',
      'low_priority',
    )
  })

  it('changes the verdict the AI gave', async () => {
    const { cards, change, find } = await open(two('cleared'))

    await cards()[0]?.find('[data-test="cleared-other"]').trigger('click')
    await flushPromises()

    expect(change).toHaveBeenCalledWith(4, { verdict: 'low_priority' }, 'a-security-token')
    expect(find('cleared-notice').text()).toBe('You changed 1 incident.')
  })

  it('takes one back', async () => {
    const { cards, takeBack, find } = await open(two('cleared'))
    takeBack.mockResolvedValue(changed(1, 1))

    await cards()[0]?.find('[data-test="cleared-take-back"]').trigger('click')
    await flushPromises()

    expect(takeBack).toHaveBeenCalledWith([{ kind: 'cleared', id: 4 }], 'a-security-token')
    expect(find('cleared-notice').text()).toBe(
      'You took back 1 incident. 1 incident was no longer there.',
    )
  })

  it('says how many were no longer there, of several', async () => {
    const { cards, confirm, find } = await open(two())
    confirm.mockResolvedValue(changed(0, 2))

    await cards()[0]?.find('[data-test="cleared-confirm"]').trigger('click')
    await flushPromises()

    expect(find('cleared-notice').text()).toBe(
      'You confirmed 0 incidents. 2 incidents were no longer there.',
    )
  })

  it('says when it could not', async () => {
    const { cards, confirm, find } = await open()
    confirm.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await cards()[0]?.find('[data-test="cleared-confirm"]').trigger('click')
    await flushPromises()

    expect(find('cleared-failure').text()).toBe('Could not save.')
  })

  describe('many at once', () => {
    it('offers nothing to do until some are picked, and picks them all', async () => {
      const { find, cards } = await open(two())
      expect(find('cleared-confirm-picked').exists()).toBe(false)

      await cards()[0]?.find('[data-test="cleared-pick"]').setValue(true)
      expect(find('cleared-confirm-picked').text()).toBe('Confirm 1')
      expect(find('cleared-pick-all').element).toHaveProperty('checked', false)

      await find('cleared-pick-all').setValue(true)
      expect(find('cleared-confirm-picked').text()).toBe('Confirm 2')
      expect(find('cleared-pick-all').element).toHaveProperty('checked', true)

      await find('cleared-pick-all').setValue(false)
      expect(find('cleared-confirm-picked').exists()).toBe(false)

      await cards()[0]?.find('[data-test="cleared-pick"]').setValue(true)
      await cards()[0]?.find('[data-test="cleared-pick"]').setValue(false)
      expect(find('cleared-confirm-picked').exists()).toBe(false)
    })

    it('confirms those picked', async () => {
      const { find, confirm } = await open(two())
      confirm.mockResolvedValue(changed(2))

      await find('cleared-pick-all').setValue(true)
      await find('cleared-confirm-picked').trigger('click')
      await flushPromises()

      expect(confirm).toHaveBeenCalledWith(
        [
          { kind: 'waiting', id: 4 },
          { kind: 'waiting', id: 5 },
        ],
        'a-security-token',
        undefined,
      )
      expect(find('cleared-notice').text()).toBe('You confirmed 2 incidents.')
    })

    it('takes back those picked, after asking', async () => {
      const { find, takeBack, fetchIt } = await open(two('cleared'))
      takeBack.mockResolvedValue(changed(2))

      await find('cleared-pick-all').setValue(true)
      await find('cleared-take-back-picked').trigger('click')
      await flushPromises()
      expect(takeBack).not.toHaveBeenCalled()

      fetchIt.mockResolvedValue(clearedPage({ state: 'cleared', total: 0, items: [] }))
      document.querySelector<HTMLElement>('[data-test="confirm-accept"]')?.click()
      await flushPromises()

      expect(takeBack).toHaveBeenCalledWith(
        [
          { kind: 'cleared', id: 4 },
          { kind: 'cleared', id: 5 },
        ],
        'a-security-token',
      )
      expect(find('cleared-notice').text()).toBe('You took back 2 incidents.')
    })

    it('does not take back when the question is put away', async () => {
      const { find, takeBack } = await open(two('cleared'))

      await find('cleared-pick-all').setValue(true)
      await find('cleared-take-back-picked').trigger('click')
      await flushPromises()
      document.querySelector<HTMLElement>('[data-test="confirm-cancel"]')?.click()
      await flushPromises()

      expect(takeBack).not.toHaveBeenCalled()
    })

    it('forgets a pick of something that is gone', async () => {
      const { find, fetchIt, wrapper } = await open(two())
      await find('cleared-pick-all').setValue(true)
      fetchIt.mockResolvedValue(clearedPage({ total: 1, items: [clearedItem({ id: 5 })] }))

      wrapper.findComponent({ name: 'ClearedCard' }).vm.$emit('confirm')
      await flushPromises()

      expect(find('cleared-confirm-picked').text()).toBe('Confirm 1')
    })

    it('forgets the picks when the list changes', async () => {
      const { find, fetchIt, wrapper } = await open(two())
      await find('cleared-pick-all').setValue(true)
      fetchIt.mockResolvedValue(two('cleared'))

      await wrapper.find('[data-test="cleared-list-cleared"]').trigger('click')
      await flushPromises()

      expect(find('cleared-confirm-picked').exists()).toBe(false)
    })
  })

  it('shows more when there are more', async () => {
    const { find, fetchIt, cards } = await open(clearedPage({ total: 25 }))
    expect(find('cleared-more').text()).toBe('Show 20 more (24 left)')
    fetchIt.mockResolvedValue(
      clearedPage({ total: 25, items: [clearedItem({ id: 8 }), clearedItem({ id: 9 })] }),
    )

    await find('cleared-more').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith('waiting', 20, 1)
    expect(cards()).toHaveLength(3)
  })

  it('says when showing more failed', async () => {
    const { find, fetchIt } = await open(clearedPage({ total: 25 }))
    fetchIt.mockRejectedValue(offline())

    await find('cleared-more').trigger('click')
    await flushPromises()

    expect(find('cleared-failure').text()).toContain("Can't reach AresGate.")
  })
})
