import VerdictRow from '@/components/VerdictRow.vue'
import { mountWithPlugins } from '@/test/mount'
import { verdict } from '@/test/verdicts'

const HOUR = 3_600_000

async function show(changes: Parameters<typeof verdict>[0] = {}) {
  const mounted = await mountWithPlugins(VerdictRow, {
    props: { rule: verdict(changes) },
    // A list item needs a list.
    slots: {},
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('VerdictRow', () => {
  it('says what was said and what it is about', async () => {
    const { text } = await show({ verdict: 'low_priority', signature: 'ET SCAN' })

    expect(text('verdict')).toBe('Low priority')
    expect(text('verdict-about')).toBe('“ET SCAN” from 93.184.216.34')
  })

  it('says why, when it was said why', async () => {
    const { text, wrapper } = await show({ note: 'my scanner' })

    expect(text('verdict-why')).toBe('Why: my scanner')
    expect((await show()).wrapper.find('[data-test="verdict-why"]').exists()).toBe(false)
    expect(wrapper.exists()).toBe(true)
  })

  it('says how many signals it has been applied to, and when the last was', async () => {
    const { text } = await show({
      hits: 12,
      last_hit_at: new Date(Date.now() - 2 * HOUR).toISOString(),
    })

    expect(text('verdict-meta')).toMatch(/^Applied to 12 signals, the last 2 hours ago · Given /)
  })

  it('says signal, not signals, for one', async () => {
    const { text } = await show({ hits: 1 })

    expect(text('verdict-meta')).toContain('Applied to 1 signal, the last')
  })

  it('says when it has not been applied to anything', async () => {
    const { text } = await show({ hits: 0, last_hit_at: null })

    expect(text('verdict-meta')).toContain('Not applied to a signal yet')
  })

  it('says when it was given, machine-readable', async () => {
    const { wrapper } = await show({ created_at: '2026-10-26T14:00:00Z' })

    expect(wrapper.find('time').attributes('datetime')).toBe('2026-10-26T14:00:00Z')
  })

  it('asks to change it, and to take it back', async () => {
    const { wrapper } = await show()

    await wrapper.find('[data-test="verdict-change"]').trigger('click')
    await wrapper.find('[data-test="verdict-remove"]').trigger('click')

    expect(wrapper.emitted('change')).toHaveLength(1)
    expect(wrapper.emitted('remove')).toHaveLength(1)
  })
})
