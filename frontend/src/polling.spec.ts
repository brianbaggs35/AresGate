import { defineComponent, h } from 'vue'

import { usePolling } from '@/polling'
import { mountWithPlugins } from '@/test/mount'

function visibility(state: 'visible' | 'hidden') {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue(state)
}

async function polled(task: () => unknown) {
  const Poller = defineComponent({
    setup() {
      usePolling(task, 30_000)
      return () => h('div')
    },
  })
  return (await mountWithPlugins(Poller)).wrapper
}

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    visibility('visible')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not run until the interval has passed', async () => {
    const task = vi.fn()
    await polled(task)
    vi.advanceTimersByTime(29_999)
    expect(task).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(task).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(30_000)
    expect(task).toHaveBeenCalledTimes(2)
  })

  it('waits while the page is out of view', async () => {
    const task = vi.fn()
    await polled(task)
    visibility('hidden')
    vi.advanceTimersByTime(90_000)
    expect(task).not.toHaveBeenCalled()
  })

  it('asks at once when the page comes back after longer than the interval', async () => {
    const task = vi.fn()
    await polled(task)
    visibility('hidden')
    vi.advanceTimersByTime(90_000)
    visibility('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('does not ask again when the page comes back soon after it last did', async () => {
    const task = vi.fn()
    await polled(task)
    vi.advanceTimersByTime(30_000)
    expect(task).toHaveBeenCalledTimes(1)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('ignores a page that is going out of view', async () => {
    const task = vi.fn()
    await polled(task)
    vi.advanceTimersByTime(60_000)
    task.mockClear()
    visibility('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(task).not.toHaveBeenCalled()
  })

  it('stops when the component goes', async () => {
    const task = vi.fn()
    const wrapper = await polled(task)
    wrapper.unmount()
    vi.advanceTimersByTime(120_000)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(task).not.toHaveBeenCalled()
  })
})
