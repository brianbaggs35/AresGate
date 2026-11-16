import { defineComponent, h } from 'vue'

import { mountWithPlugins } from '@/test/mount'
import { useServerEvents } from '@/serverEvents'

class FakeSource {
  static made: FakeSource[] = []
  listeners = new Map<string, () => void>()
  closed = false

  constructor(public url: string) {
    FakeSource.made.push(this)
  }

  addEventListener(name: string, listener: () => void) {
    this.listeners.set(name, listener)
  }

  close() {
    this.closed = true
  }

  say(name: string) {
    this.listeners.get(name)?.()
  }
}

function listen(onChange: () => void) {
  let live: ReturnType<typeof useServerEvents>['live'] | undefined
  const Page = defineComponent({
    setup() {
      live = useServerEvents('/api/stream', onChange).live
      return () => h('div')
    },
  })
  return mountWithPlugins(Page).then(({ wrapper }) => ({ wrapper, live: () => live!.value }))
}

describe('useServerEvents', () => {
  beforeEach(() => {
    FakeSource.made = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('connects to the stream when the page is on screen, and is live once it says it is ready', async () => {
    const { live } = await listen(() => undefined)

    expect(FakeSource.made.map((source) => source.url)).toEqual(['/api/stream'])
    expect(live()).toBe(false)

    FakeSource.made[0]!.say('ready')

    expect(live()).toBe(true)
  })

  it('calls back each time the server says something changed', async () => {
    const onChange = vi.fn()
    await listen(onChange)

    FakeSource.made[0]!.say('changed')
    FakeSource.made[0]!.say('changed')

    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('is not live while the connection is broken', async () => {
    const { live } = await listen(() => undefined)
    FakeSource.made[0]!.say('ready')

    FakeSource.made[0]!.say('error')

    expect(live()).toBe(false)
  })

  it('lets go of the stream when the page goes', async () => {
    const { wrapper, live } = await listen(() => undefined)
    FakeSource.made[0]!.say('ready')

    wrapper.unmount()

    expect(FakeSource.made[0]!.closed).toBe(true)
    expect(live()).toBe(false)
  })

  it('does nothing in a browser that has no event source', async () => {
    vi.unstubAllGlobals()
    vi.stubGlobal('EventSource', undefined)

    const { wrapper, live } = await listen(() => undefined)
    wrapper.unmount()

    expect(live()).toBe(false)
    expect(FakeSource.made).toEqual([])
  })
})
