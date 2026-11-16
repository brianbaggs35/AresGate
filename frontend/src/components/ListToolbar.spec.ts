import * as viewsApi from '@/api/views'
import ListToolbar from '@/components/ListToolbar.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { kept } from '@/test/views'

async function show(
  options: { route?: string; width?: number; views?: viewsApi.SavedView[] } = {},
) {
  vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue(options.views ?? [])
  const mounted = await mountWithPlugins(ListToolbar, {
    signedIn: 'admin',
    route: options.route ?? '/incidents',
    width: options.width ?? 1280,
    props: { list: 'incidents', asked: new URLSearchParams('status=open') },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const inBody = (selector: string) => document.querySelector<HTMLElement>(selector)
  return { ...mounted, find, inBody }
}

describe('ListToolbar', () => {
  it('has an Export and a Views button on a computer', async () => {
    const { find } = await show()

    expect(find('list-export').text()).toBe('Export')
    expect(find('list-views-button').text()).toBe('Views')
    expect(find('list-options').exists()).toBe(false)
  })

  it('opens the file of the list from the Export button', async () => {
    const { find, inBody } = await show()

    await find('list-export').trigger('click')
    await flushPromises()

    expect(inBody('[data-test="export-panel"]')).not.toBeNull()
    expect(inBody('[data-test="export-csv"]')?.getAttribute('href')).toContain(
      '/api/incidents/export?status=open&format=csv',
    )
    expect(inBody('[data-test="views-panel"]')).toBeNull()
  })

  it('opens the views from the Views button', async () => {
    const { find, inBody } = await show({ views: [kept({ name: 'Needs a look' })] })

    await find('list-views-button').trigger('click')
    await flushPromises()

    expect(inBody('[data-test="views-panel"]')?.textContent).toContain('Needs a look')
    expect(inBody('[data-test="export-panel"]')).toBeNull()
  })

  it('is one menu holding both on a phone', async () => {
    const { find, inBody } = await show({ width: 400 })

    expect(find('list-export').exists()).toBe(false)
    expect(find('list-views-button').exists()).toBe(false)

    await find('list-options').trigger('click')
    await flushPromises()

    const panel = inBody('[data-test="list-panel"]')
    expect(panel?.querySelector('[data-test="list-export"]')).not.toBeNull()
    expect(panel?.querySelector('[data-test="list-views"]')).not.toBeNull()
  })

  describe('the view a page opens on', () => {
    const chosen = kept({ name: 'Mine', is_default: true, query: { view: 'all', q: 'ssh' } })

    it('is set when the page is opened bare', async () => {
      const { router } = await show({ views: [kept({ id: 2 }), chosen] })

      await vi.waitFor(() => {
        expect(router.currentRoute.value.query).toEqual({ view: 'all', q: 'ssh' })
      })
    })

    it('is left alone when the address already has filters', async () => {
      const { router } = await show({ route: '/incidents?severity=high', views: [chosen] })

      expect(router.currentRoute.value.query).toEqual({ severity: 'high' })
    })

    it('is not set when there is none, or it is another page’s', async () => {
      const { router } = await show({
        views: [kept({ page: 'assets', is_default: true, query: { new: 'true' } })],
      })

      expect(router.currentRoute.value.query).toEqual({})
    })
  })
})
