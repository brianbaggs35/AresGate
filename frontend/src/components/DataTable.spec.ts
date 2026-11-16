import DataTable from '@/components/DataTable.vue'
import { mountWithPlugins } from '@/test/mount'

const slots = { default: '<table><tbody><tr><th>Name</th><td>Value</td></tr></tbody></table>' }

describe('DataTable', () => {
  it('holds a table in a region a screen reader can name', async () => {
    const { wrapper } = await mountWithPlugins(DataTable, { props: { label: 'Incidents' }, slots })
    const region = wrapper.find('[data-test="data-table"]')

    expect(region.element.tagName).toBe('SECTION')
    expect(region.attributes('aria-label')).toBe('Incidents')
    expect(region.find('table').exists()).toBe(true)
  })

  it('keeps the first column in place only when asked to', async () => {
    const plain = await mountWithPlugins(DataTable, { props: { label: 'A' }, slots })
    const pinned = await mountWithPlugins(DataTable, {
      props: { label: 'B', stickyFirst: true },
      slots,
    })

    expect(plain.wrapper.classes()).not.toContain('data-table--sticky-first')
    expect(pinned.wrapper.classes()).toContain('data-table--sticky-first')
  })
})
