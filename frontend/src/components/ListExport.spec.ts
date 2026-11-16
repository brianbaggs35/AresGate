import ListExport from '@/components/ListExport.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ListExport', () => {
  it('links to a file in each format of what the list asked for', async () => {
    const { wrapper } = await mountWithPlugins(ListExport, {
      props: { list: 'devices', asked: new URLSearchParams('scope=local&sort=busiest') },
    })

    const link = (name: string) =>
      wrapper.find(`[data-test="${name}"]`).attributes('href') as string
    const csv = new URL(link('export-csv'), 'https://example.test')
    const json = new URL(link('export-json'), 'https://example.test')

    expect(csv.pathname).toBe('/api/devices/export')
    expect(csv.searchParams.get('format')).toBe('csv')
    expect(csv.searchParams.get('scope')).toBe('local')
    expect(csv.searchParams.get('sort')).toBe('busiest')
    expect(json.searchParams.get('format')).toBe('json')
    expect(wrapper.find('[data-test="export-csv"]').attributes('download')).toBeDefined()
  })

  it('says what is in the file, and is a labelled section', async () => {
    const { wrapper } = await mountWithPlugins(ListExport, {
      props: { list: 'assets', asked: new URLSearchParams() },
    })

    expect(wrapper.text()).toContain('up to 10,000 rows')
    expect(wrapper.find('section').attributes('aria-labelledby')).toBeTruthy()
  })
})
