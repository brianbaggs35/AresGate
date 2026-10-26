import NotFoundView from '@/views/NotFoundView.vue'
import { mountWithPlugins } from '@/test/mount'

describe('NotFoundView', () => {
  it('says the page is missing and links back to the dashboard', async () => {
    const { wrapper } = await mountWithPlugins(NotFoundView)
    expect(wrapper.text()).toContain('Page not found')
    expect(wrapper.find('a').attributes('href')).toBe('/')
  })
})
