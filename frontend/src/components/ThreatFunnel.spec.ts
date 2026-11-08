import ThreatFunnel from '@/components/ThreatFunnel.vue'
import { mountWithPlugins } from '@/test/mount'
import { funnel } from '@/test/threats'

describe('ThreatFunnel', () => {
  it('says it in a sentence and then step by step, each with its number', async () => {
    const { wrapper } = await mountWithPlugins(ThreatFunnel, {
      props: { funnel: funnel(), window: 'the last 24 hours' },
    })

    expect(wrapper.find('[data-test="funnel-sentence"]').text()).toContain(
      '70,412 reports in the last 24 hours came to 1,204 alerts',
    )
    const count = (key: string) =>
      wrapper.find(`[data-test="funnel-${key}"] [data-test="funnel-count"]`).text()
    expect(
      ['reports', 'alerts', 'incidents', 'threat', 'suspect', 'background'].map(count),
    ).toEqual(['70,412', '1,204', '63', '2', '5', '50'])
  })

  it('colors the lanes as their chips are and the rest in the theme’s', async () => {
    const { wrapper } = await mountWithPlugins(ThreatFunnel, {
      props: { funnel: funnel(), window: 'the last 7 days' },
    })

    const bar = (key: string) =>
      wrapper.find(`[data-test="funnel-${key}"] .funnel__bar`).attributes('style') ?? ''
    expect(bar('threat')).toContain('--v-theme-error')
    expect(bar('suspect')).toContain('--v-theme-warning')
    expect(bar('background')).toContain('--v-theme-secondary')
    expect(bar('reports')).toContain('--v-theme-primary')
  })
})
