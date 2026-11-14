import AiGaveChip from '@/components/AiGaveChip.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(ai: { confidence: number; provider: string | null; model: string | null }) {
  const { wrapper } = await mountWithPlugins(AiGaveChip, { props: { ai } })
  return wrapper.find('[data-test="ai-gave"]')
}

describe('AiGaveChip', () => {
  it('says the AI gave it and how sure it was, and which AI in the tooltip', async () => {
    const chip = await show({ confidence: 91, provider: 'anthropic', model: 'claude-haiku-5-5' })

    expect(chip.text()).toBe('Given by the AI, 91% sure')
    expect(chip.attributes('title')).toBe('Said by anthropic claude-haiku-5-5')
  })

  it('does not name an AI it does not know', async () => {
    const chip = await show({ confidence: 80, provider: null, model: null })

    expect(chip.attributes('title')).toBe('Said by the AI')
  })
})
