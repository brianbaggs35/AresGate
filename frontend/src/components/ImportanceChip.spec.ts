import type { Touched } from '@/api/incidents'
import ImportanceChip from '@/components/ImportanceChip.vue'
import { mountWithPlugins } from '@/test/mount'

const touched = (changes: Partial<Touched> = {}): Touched => ({
  name: 'vault',
  kind: 'Storage (NAS)',
  importance: 'critical',
  text: 'It touched vault, a storage (nas) you marked critical.',
  ...changes,
})

describe('ImportanceChip', () => {
  it.each([
    ['critical', 'Critical device', 'v-chip--variant-flat'],
    ['important', 'Important device', 'v-chip--variant-flat'],
    ['low', 'Guest or IoT only', 'v-chip--variant-outlined'],
  ] as const)('names a %s device in words and says which one', async (importance, label, look) => {
    const { wrapper } = await mountWithPlugins(ImportanceChip, {
      props: { touched: touched({ importance, text: `About ${importance}.` }) },
    })

    const chip = wrapper.find('[data-test="importance-chip"]')
    expect(chip.text()).toBe(label)
    expect(chip.classes()).toContain(look)
    expect(chip.attributes('title')).toBe(`About ${importance}.`)
  })
})
