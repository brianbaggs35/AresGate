import WidgetNeeds from '@/components/WidgetNeeds.vue'
import { mountWithPlugins } from '@/test/mount'

describe('WidgetNeeds', () => {
  it('says what the widget would show and what to connect, with the way to Integrations', async () => {
    const { wrapper } = await mountWithPlugins(WidgetNeeds, {
      props: { title: 'Traffic', words: 'Connect OPNsense or ntopng to see this.' },
    })

    expect(wrapper.find('h2').text()).toBe('Traffic')
    expect(wrapper.find('[data-test="widget-needs-words"]').text()).toBe(
      'Connect OPNsense or ntopng to see this.',
    )
    expect(wrapper.find('[data-test="widget-needs-link"]').attributes('href')).toBe('/integrations')
  })
})
