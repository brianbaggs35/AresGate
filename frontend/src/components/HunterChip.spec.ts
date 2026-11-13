import HunterChip from '@/components/HunterChip.vue'
import { mountWithPlugins } from '@/test/mount'

const flag = (changes = {}) => ({
  agent_id: 3,
  agent_name: 'Night watch',
  run_id: 9,
  finished_at: '2026-11-10T12:00:00Z',
  severity: 'high',
  title: 'Looks real',
  action: '',
  confidence: 'high',
  ...changes,
})

describe('HunterChip', () => {
  it('names the hunter that flagged the incident, and says what each said on hover', async () => {
    const { wrapper } = await mountWithPlugins(HunterChip, {
      props: { flags: [flag(), flag({ agent_name: 'Other', severity: 'medium', title: 'Maybe' })] },
    })

    const chip = wrapper.find('[data-test="hunter-chip"]')
    expect(chip.text()).toBe('Flagged by Night watch')
    expect(chip.attributes('title')).toBe('Night watch (high): Looks real\nOther (medium): Maybe')
  })

  it('shows nothing when nothing was flagged', async () => {
    const { wrapper } = await mountWithPlugins(HunterChip, { props: { flags: [] } })

    expect(wrapper.find('[data-test="hunter-chip"]').exists()).toBe(false)
  })
})
