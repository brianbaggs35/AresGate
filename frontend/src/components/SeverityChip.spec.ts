import SeverityChip from '@/components/SeverityChip.vue'
import { SEVERITIES, SEVERITY, type Severity } from '@/severity'
import { mountWithPlugins } from '@/test/mount'

describe('SeverityChip', () => {
  it.each<[Severity, string]>([
    ['info', 'Info'],
    ['low', 'Low'],
    ['medium', 'Medium'],
    ['high', 'High'],
    ['critical', 'Critical'],
  ])('says %s in words', async (severity, words) => {
    const { wrapper } = await mountWithPlugins(SeverityChip, { props: { severity } })
    expect(wrapper.find('[data-test="severity"]').text()).toBe(words)
  })

  it('draws the most serious solid, and the rest tinted', async () => {
    const critical = await mountWithPlugins(SeverityChip, { props: { severity: 'critical' } })
    expect(critical.wrapper.find('.v-chip').classes()).toContain('v-chip--variant-flat')
    const high = await mountWithPlugins(SeverityChip, { props: { severity: 'high' } })
    expect(high.wrapper.find('.v-chip').classes()).toContain('v-chip--variant-tonal')
  })

  it('gives each its own icon, so color is never all there is', () => {
    const icons = SEVERITIES.map((severity) => SEVERITY[severity].icon)
    expect(new Set(icons).size).toBe(SEVERITIES.length)
  })
})
