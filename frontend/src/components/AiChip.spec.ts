import AiChip from '@/components/AiChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AiChip', () => {
  it('says it is the AI’s word for it and how sure the AI is', async () => {
    const { wrapper } = await mountWithPlugins(AiChip, {
      props: { ai: { classification: 'probe', confidence: 91 } },
    })

    const chip = wrapper.find('[data-test="ai-chip"]')
    expect(chip.text()).toBe('AI: Probe, 91% sure')
    expect(chip.attributes('title')).toContain("The AI's opinion")
  })

  it('has a name for the worst of it too', async () => {
    const { wrapper } = await mountWithPlugins(AiChip, {
      props: { ai: { classification: 'compromise', confidence: 85 } },
    })

    expect(wrapper.text()).toBe('AI: Possible compromise, 85% sure')
  })
})
