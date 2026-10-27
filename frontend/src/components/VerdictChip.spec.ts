import type { VerdictKind } from '@/api/verdicts'
import VerdictChip from '@/components/VerdictChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('VerdictChip', () => {
  it.each<[VerdictKind, string]>([
    ['not_suspicious', 'Not suspicious'],
    ['low_priority', 'Low priority'],
    ['threat', 'Real threat'],
  ])('says %s in words, and what it means', async (verdict, words) => {
    const { wrapper } = await mountWithPlugins(VerdictChip, { props: { verdict } })

    const chip = wrapper.find('[data-test="verdict"]')
    expect(chip.text()).toBe(words)
    expect(chip.attributes('title')).not.toBe('')
  })

  it('can be small', async () => {
    const { wrapper } = await mountWithPlugins(VerdictChip, {
      props: { verdict: 'threat', size: 'small' },
    })

    expect(wrapper.find('[data-test="verdict"]').classes()).toContain('v-chip--size-small')
  })
})
