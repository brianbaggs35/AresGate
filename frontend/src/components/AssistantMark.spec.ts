import AssistantMark from '@/components/AssistantMark.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AssistantMark', () => {
  it('is decorative, at the size it was given', async () => {
    const { wrapper } = await mountWithPlugins(AssistantMark, { props: { size: 40 } })
    const mark = wrapper.find('.mark')
    expect(mark.attributes('aria-hidden')).toBe('true')
    expect(mark.attributes('style')).toContain('--mark-size: 40px')
    expect(mark.classes()).not.toContain('mark--busy')
  })

  it('is 32 pixels unless told otherwise, and breathes while the assistant works', async () => {
    const { wrapper } = await mountWithPlugins(AssistantMark, { props: { busy: true } })
    const mark = wrapper.find('.mark')
    expect(mark.attributes('style')).toContain('--mark-size: 32px')
    expect(mark.classes()).toContain('mark--busy')
  })
})
