import type { LogVolume } from '@/api/logs'
import LogVolumeChart from '@/components/LogVolume.vue'
import { mountWithPlugins } from '@/test/mount'

const volume: LogVolume = {
  start: '2026-10-27T08:00:00Z',
  seconds: 300,
  counts: [
    [0, 0, 2, 0, 0],
    [0, 0, 1, 3, 0],
  ],
}

const open = (props: Record<string, unknown> = {}) =>
  mountWithPlugins(LogVolumeChart, {
    props: { volume, matched: 6, capped: false, ...props },
  })

describe('LogVolume', () => {
  it('draws a stack for each stretch of time, by severity', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="log-volume"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="bar"]')).toHaveLength(3)
    expect(wrapper.findAll('[data-test="bar-slot"]')).toHaveLength(2)
  })

  it('says how many events it is of, and that it is the newest when there were more', async () => {
    const { wrapper } = await open()
    expect(wrapper.text()).toContain('6 events found. Pick a bar')

    await wrapper.setProps({ matched: 1 })
    expect(wrapper.text()).toContain('1 event found')

    await wrapper.setProps({ matched: 50_000, capped: true })
    expect(wrapper.text()).toMatch(/The newest 50,000 events found/)
  })

  it('says which stretch of time was picked, as a search can say it', async () => {
    const { wrapper } = await open()

    await wrapper.findAll('[data-test="bar-slot"]')[1]?.trigger('click')

    expect(wrapper.emitted('range')).toEqual([
      [{ start: '2026-10-27T08:05:00Z', end: '2026-10-27T08:10:00Z' }],
    ])
  })

  it('shows the chart as loading while a new search is on its way', async () => {
    const { wrapper } = await open({ loading: true })

    expect(wrapper.findComponent({ name: 'BarChart' }).props('loading')).toBe(true)
  })

  it('says there are no events when there is nothing to draw', async () => {
    const { wrapper } = await open({ volume: null, matched: 0 })

    expect(wrapper.text()).toContain('No events')
    expect(wrapper.text()).toContain('Nothing matches this search.')
  })

  it('ignores a pick of a bar that is not there', async () => {
    const { wrapper } = await open({ volume: null, matched: 0 })
    const chart = wrapper.findComponent({ name: 'BarChart' })

    chart.vm.$emit('select', 4)

    expect(wrapper.emitted('range')).toBeUndefined()
  })
})
