import BaselineInterface from '@/components/BaselineInterface.vue'
import { mountWithPlugins } from '@/test/mount'
import { deviation, series } from '@/test/baselines'

async function open(changes: Parameters<typeof series>[0] = {}) {
  const { wrapper } = await mountWithPlugins(BaselineInterface, {
    props: { series: series(changes) },
  })
  const text = (name: string) => wrapper.find(`[data-test="${name}"]`).text()
  return { wrapper, text }
}

describe('BaselineInterface', () => {
  it('is titled by what you call the interface and the direction', async () => {
    const { wrapper } = await open()

    expect(wrapper.text()).toContain('Home: received')
  })

  it('falls back to the name the integration uses, and then to something said plainly', async () => {
    const named = await open({ name: null })
    const unnamed = await open({ name: null, interface: null, direction: 'sent' })

    expect(named.wrapper.text()).toContain('igc0: received')
    expect(unnamed.wrapper.text()).toContain('An interface: sent')
  })

  it('says when it is busiest and quietest, and from how many hours it learned', async () => {
    const { text, wrapper } = await open()

    expect(text('baseline-extremes')).toBe(
      'Busiest at 18:00 with 400.0 MB, quietest at 00:00 with 100.0 MB.',
    )
    expect(wrapper.text()).toContain('learned from up to 28 hours')
  })

  it('finds the busiest and quietest hour wherever they are', async () => {
    const hours = series().hours.map((hour) => ({
      ...hour,
      median: hour.hour === 3 ? 900 : hour.hour === 20 ? 5 : 100,
    }))
    const { text } = await open({ hours })

    expect(text('baseline-extremes')).toBe(
      'Busiest at 03:00 with 900 B, quietest at 20:00 with 5 B.',
    )
  })

  it('draws a bar for each hour of the day', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="baseline-chart"]').exists()).toBe(true)
  })

  it('lists the hours lately that were far above usual', async () => {
    const { text } = await open({ deviations: [deviation()] })

    expect(text('baseline-deviations')).toContain('900.0 MB against 100.0 MB usual.')
  })

  it('says when nothing was', async () => {
    const { text } = await open()

    expect(text('baseline-calm')).toBe('Nothing was far above usual in the last month.')
  })
})
