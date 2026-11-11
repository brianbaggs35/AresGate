import TrustRow from '@/components/TrustRow.vue'
import { trustRule } from '@/test/trust'
import { mountWithPlugins } from '@/test/mount'

async function row(changes = {}) {
  const mounted = await mountWithPlugins(TrustRow, {
    props: { rule: trustRule(changes) },
    signedIn: 'admin',
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('TrustRow', () => {
  it('says what is trusted, how much, and what it has kept quiet', async () => {
    const { text } = await row()

    expect(text('trust-about')).toBe('Everything about 52.1.2.3')
    expect(text('trust-level')).toBe('Safe')
    expect(text('trust-applied')).toContain('Kept 12 alerts in 2 incidents from raising an alarm')
    expect(text('trust-applied')).toContain('last')
  })

  it('opens the decision', async () => {
    const { wrapper } = await row({ id: 7 })

    expect(wrapper.find('[data-test="trust-open"]').attributes('href')).toBe('/trust/7')
  })

  it('shows the note, quoted, only when there is one', async () => {
    const withNote = await row({ note: 'Blink camera' })
    expect(withNote.text('trust-note')).toBe('“Blink camera”')

    const without = await row({ note: null })
    expect(without.wrapper.find('[data-test="trust-note"]').exists()).toBe(false)
  })

  it('says a decision that has kept nothing quiet has not been applied', async () => {
    const { text } = await row({ hits: 0, incidents: 0, last_hit_at: null })

    expect(text('trust-applied')).toBe('Not applied to anything yet')
  })

  it('says low priority for a decision that is only that', async () => {
    const { text } = await row({ verdict: 'low_priority' })

    expect(text('trust-level')).toBe('Low priority')
  })

  it('asks to take it back by a button that says which, without opening the decision', async () => {
    const { wrapper } = await row()
    const button = wrapper.find('[data-test="trust-revoke"]')

    expect(button.attributes('aria-label')).toBe('Take back: Everything about 52.1.2.3')
    await button.trigger('click')

    expect(wrapper.emitted('revoke')).toHaveLength(1)
  })
})
