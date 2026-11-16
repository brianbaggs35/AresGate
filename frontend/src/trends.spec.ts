import { flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import {
  activityOf,
  deliverySeries,
  hourLabel,
  looksLikeAddress,
  sparkLabel,
  stripSummary,
  useTrend,
} from '@/trends'
import { mountWithPlugins } from '@/test/mount'
import { addressTrends, deliveryTrend } from '@/test/trends'

describe('deliverySeries', () => {
  it('has the severities there were any of, least serious first', () => {
    const found = deliverySeries(deliveryTrend())

    expect(found.map(({ id }) => id)).toEqual(['medium', 'high'])
    expect(found.map(({ values }) => values)).toEqual([
      [0, 1, 0],
      [2, 0, 1],
    ])
    expect(found[1]?.label).toBe('High')
  })

  it('has none when nothing was sent', () => {
    const none = deliveryTrend({
      severities: { info: [0], low: [0], medium: [0], high: [0], critical: [0] },
    })

    expect(deliverySeries(none)).toEqual([])
  })
})

describe('activityOf', () => {
  it('adds the connections in and out of an address', () => {
    expect(activityOf(addressTrends(), '192.168.1.20')).toEqual([1, 3, 3])
  })

  it('has nothing for an address that was not asked about', () => {
    expect(activityOf(addressTrends(), '10.0.0.1')).toBeNull()
  })
})

describe('sparkLabel', () => {
  it('says how much there was and how much lately', () => {
    expect(sparkLabel('events', [1, 2000, 3], 'the last 7 days')).toBe(
      '2,004 events in the last 7 days, 3 in the latest.',
    )
  })

  it('says when there was nothing', () => {
    expect(sparkLabel('events', [0, 0], 'the last 7 days')).toBe('No events in the last 7 days.')
  })
})

describe('looksLikeAddress', () => {
  it.each(['192.168.1.20', '2001:db8::1', '::1', 'FE80::1'])('takes %s', (text) => {
    expect(looksLikeAddress(text)).toBe(true)
  })

  it.each(['laptop', 'example.test', '', '1.2.3', 'a rule'])('leaves out %s', (text) => {
    expect(looksLikeAddress(text)).toBe(false)
  })
})

describe('stripSummary', () => {
  it('counts the hours that worked and the ones with a problem', () => {
    expect(stripSummary(['ok', 'ok', 'problem', 'none'])).toBe(
      'In the last 4 hours: 2 hours working, 1 with a problem.',
    )
    expect(stripSummary(['ok', 'none'])).toBe(
      'In the last 2 hours: 1 hour working, 0 with a problem.',
    )
  })

  it('says when no calls were made', () => {
    expect(stripSummary(['none', 'none'])).toBe('No calls in the last 2 hours.')
  })
})

describe('hourLabel', () => {
  it('names the weekday and the hour', () => {
    expect(hourLabel('2026-11-16T14:00:00Z')).toMatch(/\w/)
  })
})

describe('useTrend', () => {
  async function open(ask: () => Promise<string>, initial: string | null = 'a') {
    const key = ref<string | null>(initial)
    let loading = false
    let found: string | null = null
    const Probe = defineComponent({
      setup() {
        const { trend, loading: busy } = useTrend(() => key.value, ask)
        return () => {
          loading = busy.value
          found = trend.value
          return h('div')
        }
      },
    })
    const { wrapper } = await mountWithPlugins(Probe, { signedIn: 'admin' })
    await flushPromises()
    return { wrapper, key, state: () => ({ loading, found }) }
  }

  it('loads once there is something to ask about, and again when it changes', async () => {
    const ask = vi.fn().mockResolvedValueOnce('first').mockResolvedValueOnce('second')
    const { key, state } = await open(ask)
    expect(state()).toEqual({ loading: false, found: 'first' })

    key.value = 'b'
    await flushPromises()

    expect(state().found).toBe('second')
  })

  it('is not there when there is nothing to ask about', async () => {
    const ask = vi.fn().mockResolvedValue('first')
    const { key, state } = await open(ask)

    key.value = null
    await flushPromises()

    expect(state()).toEqual({ loading: false, found: null })
  })

  it('is not there, and not an error, when it cannot be had', async () => {
    const { state } = await open(() => Promise.reject(new Error('down')))

    expect(state()).toEqual({ loading: false, found: null })
  })

  it('keeps the answer to the newest question', async () => {
    const answers: ((value: string) => void)[] = []
    const ask = () => new Promise<string>((resolve) => answers.push(resolve))
    const { key, state } = await open(ask)
    key.value = 'b'
    await flushPromises()

    answers[1]?.('newer')
    await flushPromises()
    answers[0]?.('older')
    await flushPromises()

    expect(state()).toEqual({ loading: false, found: 'newer' })
  })

  it('drops the answer to an older question that fails after a newer one', async () => {
    const rejects: ((error: Error) => void)[] = []
    const resolves: ((value: string) => void)[] = []
    let calls = 0
    const ask = () =>
      new Promise<string>((resolve, reject) => {
        calls++
        resolves.push(resolve)
        rejects.push(reject)
      })
    const { key, state } = await open(ask)
    key.value = 'b'
    await flushPromises()

    resolves[1]?.('newer')
    await flushPromises()
    rejects[0]?.(new Error('late'))
    await flushPromises()

    expect(calls).toBe(2)
    expect(state().found).toBe('newer')
  })
})
