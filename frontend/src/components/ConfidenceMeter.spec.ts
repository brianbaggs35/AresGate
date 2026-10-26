import ConfidenceMeter from '@/components/ConfidenceMeter.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ConfidenceMeter', () => {
  it('says how sure in a word and in a number', async () => {
    const { wrapper } = await mountWithPlugins(ConfidenceMeter, {
      props: { confidence: 70, level: 'high' },
    })

    expect(wrapper.find('[data-test="confidence-level"]').text()).toBe('High confidence')
    expect(wrapper.find('[data-test="confidence-value"]').text()).toBe('70 of 100')
    expect(wrapper.find('[data-test="confidence-level"]').attributes('data-level')).toBe('high')
  })

  it.each([
    ['low', 'Low confidence'],
    ['medium', 'Medium confidence'],
  ] as const)('names %s', async (level, words) => {
    const { wrapper } = await mountWithPlugins(ConfidenceMeter, {
      props: { confidence: 20, level },
    })

    expect(wrapper.find('[data-test="confidence-level"]').text()).toBe(words)
  })

  it('draws the number as a bar that has a name of its own', async () => {
    const { wrapper } = await mountWithPlugins(ConfidenceMeter, {
      props: { confidence: 42, level: 'medium' },
    })

    const bar = wrapper.find('.v-progress-linear')
    expect(bar.attributes('aria-label')).toBe('Confidence 42 out of 100')
    expect(bar.attributes('aria-valuenow')).toBe('42')
  })

  it('is bigger at the top of a page', async () => {
    const small = await mountWithPlugins(ConfidenceMeter, {
      props: { confidence: 42, level: 'medium' },
    })
    const large = await mountWithPlugins(ConfidenceMeter, {
      props: { confidence: 42, level: 'medium', large: true },
    })

    expect(small.wrapper.find('[data-test="confidence-level"]').classes()).toContain(
      'text-label-large',
    )
    expect(large.wrapper.find('[data-test="confidence-level"]').classes()).toContain(
      'text-title-large',
    )
  })
})
