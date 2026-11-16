import AppPage from '@/components/AppPage.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AppPage', () => {
  it('holds what a page puts in it', async () => {
    const { wrapper } = await mountWithPlugins(AppPage, { slots: { default: '<p>Inside</p>' } })
    expect(wrapper.find('.app-page__stack').text()).toBe('Inside')
  })

  it.each([
    [undefined, 'regular', '960px'],
    ['narrow', 'narrow', '720px'],
    ['regular', 'regular', '960px'],
    ['wide', 'wide', '1320px'],
  ])('is %s wide, and says which so a big screen can give it more', async (width, kind, pixels) => {
    const { wrapper } = await mountWithPlugins(AppPage, { props: { width } })
    expect(wrapper.find('.app-page').attributes('style')).toContain(`--page-width: ${pixels}`)
    expect(wrapper.find('.app-page').classes()).toContain(`app-page--${kind}`)
  })
})
