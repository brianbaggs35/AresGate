import ChartTable from '@/charts/ChartTable.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ChartTable', () => {
  it('lists the numbers, each row named by its first cell', async () => {
    const { wrapper } = await mountWithPlugins(ChartTable, {
      props: {
        label: 'Traffic',
        table: {
          columns: ['Interface', 'Received', 'Sent'],
          rows: [
            ['WAN', '120', '30'],
            ['LAN', 340, 80],
          ],
        },
      },
    })

    expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual([
      'Interface',
      'Received',
      'Sent',
    ])
    const rows = wrapper.findAll('[data-test="chart-table-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.find('th').attributes('scope')).toBe('row')
    expect(rows[0]?.find('th').text()).toBe('WAN')
    expect(rows[1]?.findAll('td').map((cell) => cell.text())).toEqual(['340', '80'])
  })

  it('can be scrolled with the keyboard, and says what it is', async () => {
    const { wrapper } = await mountWithPlugins(ChartTable, {
      props: { label: 'Traffic', table: { columns: ['A'], rows: [] } },
    })

    const region = wrapper.find('[data-test="chart-table"]')
    expect(region.element.tagName).toBe('SECTION')
    expect(region.attributes('tabindex')).toBe('0')
    expect(region.attributes('aria-label')).toBe('Traffic, as a table')
  })
})
