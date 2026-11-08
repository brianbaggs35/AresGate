import CallChip from '@/components/CallChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('CallChip', () => {
  it('says it is the AI’s word and how sure it is', async () => {
    const { wrapper } = await mountWithPlugins(CallChip, {
      props: { call: { classification: 'probe', confidence: 92, basis: 'family' } },
    })

    const chip = wrapper.find('[data-test="call-chip"]')
    expect(chip.text()).toBe('AI: Probe, 92% sure')
    expect(chip.attributes('title')).toContain('judged this kind of incident as a whole')
  })

  it('says it is your word, with no confidence, when it is yours', async () => {
    const { wrapper } = await mountWithPlugins(CallChip, {
      props: { call: { classification: 'noise', confidence: 100, basis: 'owner' } },
    })

    expect(wrapper.find('[data-test="call-chip"]').text()).toBe('You: Harmless')
  })

  it('says when the AI read this incident itself', async () => {
    const { wrapper } = await mountWithPlugins(CallChip, {
      props: { call: { classification: 'attack', confidence: 88, basis: 'reading' } },
    })

    expect(wrapper.find('[data-test="call-chip"]').attributes('title')).toContain(
      'The AI read this incident.',
    )
  })
})
