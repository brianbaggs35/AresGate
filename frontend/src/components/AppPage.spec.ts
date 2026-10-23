import AppPage from '@/components/AppPage.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AppPage', () => {
  it('holds what a page puts in it', async () => {
    const { wrapper } = await mountWithPlugins(AppPage, { slots: { default: '<p>Inside</p>' } })
    expect(wrapper.find('.app-page__stack').text()).toBe('Inside')
  })

  it.each([
    [undefined, '960px'],
    ['narrow', '720px'],
    ['regular', '960px'],
    ['wide', '1320px'],
  ])('is %s wide', async (width, pixels) => {
    const { wrapper } = await mountWithPlugins(AppPage, { props: { width } })
    expect(wrapper.find('.app-page').attributes('style')).toContain(`max-width: ${pixels}`)
  })
})
