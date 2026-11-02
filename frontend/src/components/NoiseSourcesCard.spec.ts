import { VSelect } from 'vuetify/components'

import NoiseSourcesCard from '@/components/NoiseSourcesCard.vue'
import { mountWithPlugins } from '@/test/mount'
import { source } from '@/test/noise'

const SOURCES = [source(), source({ key: 'ntopng', name: 'ntopng', week: {} })]

async function show(floors: Record<string, 'medium' | 'high' | 'critical'> = {}) {
  const mounted = await mountWithPlugins(NoiseSourcesCard, {
    props: { sources: SOURCES, floors },
  })
  const rows = () => mounted.wrapper.findAll('[data-test="source"]')
  return { ...mounted, rows }
}

describe('NoiseSourcesCard', () => {
  it('lists each program with what it reported this week', async () => {
    const { rows } = await show()

    expect(rows().map((row) => row.find('h3').text())).toEqual(['Wazuh', 'ntopng'])
    expect(rows().map((row) => row.find('[data-test="source-week"]').text())).toEqual([
      'Last 7 days: 12 high, 150 medium, 2,901 low.',
      'Nothing in the last 7 days.',
    ])
  })

  it('counts everything a program reports until it is told otherwise', async () => {
    const { wrapper } = await show({ ntopng: 'critical' })

    const selects = wrapper.findAllComponents(VSelect)
    expect(selects.map((select) => select.props('modelValue'))).toEqual(['all', 'critical'])
    expect(selects.map((select) => select.props('label'))).toEqual([
      'Count Wazuh alerts from',
      'Count ntopng alerts from',
    ])
  })

  it('offers everything, medium, high and critical', async () => {
    const { wrapper } = await show()

    const items = wrapper.findComponent(VSelect).props('items') as { title: string }[]
    expect(items.map((item) => item.title)).toEqual([
      'Everything it reports',
      'Medium and up',
      'High and up',
      'Critical only',
    ])
  })

  it('tells the page which program was given which floor', async () => {
    const { wrapper } = await show()

    wrapper.findAllComponents(VSelect)[1]?.vm.$emit('update:modelValue', 'high')

    expect(wrapper.emitted('change')).toEqual([['ntopng', 'high']])
  })

  it('says that no program has reported yet when none has', async () => {
    const { wrapper } = await mountWithPlugins(NoiseSourcesCard, {
      props: { sources: [], floors: {} },
    })

    expect(wrapper.find('[data-test="no-sources"]').text()).toContain(
      'No program has reported an alert yet',
    )
    expect(wrapper.find('[data-test="source-list"]').exists()).toBe(false)
  })
})
