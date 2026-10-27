import IncidentCard from '@/components/IncidentCard.vue'
import { incident } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(changes: Parameters<typeof incident>[0] = {}) {
  const mounted = await mountWithPlugins(IncidentCard, {
    props: { incident: incident(changes) },
    withApp: true,
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('IncidentCard', () => {
  it('leads to the incident', async () => {
    const { wrapper } = await show({ id: 7 })

    expect(wrapper.find('[data-test="incident"]').attributes('href')).toBe('/incidents/7')
  })

  it('says how serious it is, what it is and how sure AresGate is', async () => {
    const { wrapper, text } = await show()

    expect(text('severity')).toBe('High')
    expect(text('incident-title')).toBe('Brute force on ssh (93.184.216.34)')
    expect(text('confidence-level')).toBe('High confidence')
    expect(text('confidence-value')).toBe('70 of 100')
    expect(wrapper.find('[data-test="incident"]').attributes('style')).toContain(
      '--incident-accent: rgb(var(--v-theme-error))',
    )
  })

  it('says how many signals there were, over how long, and who saw them', async () => {
    const { text } = await show()

    expect(text('incident-signals')).toBe('3 signals over 18m')
    expect(text('incident-programs')).toBe('Seen by OPNsense, Wazuh')
  })

  it('says a single signal in the singular, with no stretch of time', async () => {
    const { text } = await show({ signal_count: 1 })

    expect(text('incident-signals')).toBe('1 signal')
  })

  it('says how long ago the last signal was, and the exact time on hover', async () => {
    const { wrapper, text } = await show()

    expect(text('incident-when')).toBe('2 minutes ago')
    expect(wrapper.find('[data-test="incident-when"]').attributes('title')).toMatch(/\d/)
    expect(wrapper.find('time').attributes('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('names the address it is about and how many others are in it', async () => {
    const { text } = await show({ addresses: ['93.184.216.34', '192.168.1.20', '192.168.1.21'] })

    expect(text('incident-subject')).toBe('93.184.216.34 and 2 other addresses')
  })

  it('says one other address in the singular', async () => {
    const { text } = await show()

    expect(text('incident-subject')).toBe('93.184.216.34 and 1 other address')
  })

  it('names just the address when there are no others', async () => {
    const { text } = await show({ addresses: ['93.184.216.34'] })

    expect(text('incident-subject')).toBe('93.184.216.34')
  })

  it('says when it is about a rule that named no address', async () => {
    const { text } = await show({ subject: 'rule:wazuh:sshd', addresses: [] })

    expect(text('incident-subject')).toBe('A rule with no address')
  })

  it('shows what was done about it, unless nothing was', async () => {
    const open = await show()
    const resolved = await show({ status: 'resolved' })

    expect(open.wrapper.find('[data-test="incident-status"]').exists()).toBe(false)
    expect(resolved.text('incident-status')).toBe('Resolved')
  })

  it('says what you said of it, unless you said nothing', async () => {
    const plain = await show()
    const quiet = await show({ verdict: 'not_suspicious' })
    const threat = await show({ verdict: 'threat' })

    expect(plain.wrapper.find('[data-test="verdict"]').exists()).toBe(false)
    expect(quiet.text('verdict')).toBe('Not suspicious')
    expect(threat.text('verdict')).toBe('Real threat')
  })

  it('says when an address was banned', async () => {
    const plain = await show()
    const banned = await show({ banned: true })

    expect(plain.wrapper.find('[data-test="incident-banned"]').exists()).toBe(false)
    expect(banned.text('incident-banned')).toBe('Banned')
  })

  it('takes its color from how serious it is', async () => {
    const { wrapper } = await show({ severity: 'low' })

    expect(wrapper.find('[data-test="incident"]').attributes('style')).toContain(
      'rgb(var(--v-theme-success))',
    )
  })
})
