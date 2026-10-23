import PageHeader from '@/components/PageHeader.vue'
import { mountWithPlugins } from '@/test/mount'

describe('PageHeader', () => {
  it('has the title as the one heading, and says what the page is for', async () => {
    const { wrapper } = await mountWithPlugins(PageHeader, {
      props: { title: 'Integrations', description: 'The systems AresGate watches.' },
    })
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.find('h1').text()).toBe('Integrations')
    expect(wrapper.find('[data-test="page-description"]').text()).toBe(
      'The systems AresGate watches.',
    )
  })

  it('leaves out what it has nothing for', async () => {
    const { wrapper } = await mountWithPlugins(PageHeader, { props: { title: 'Security' } })
    expect(wrapper.find('[data-test="page-description"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="back"]').exists()).toBe(false)
    expect(wrapper.find('.page-header__icon').exists()).toBe(false)
    expect(wrapper.find('.page-header__actions').exists()).toBe(false)
  })

  it('shows an icon, a badge, more lines and actions beside the title', async () => {
    const { wrapper } = await mountWithPlugins(PageHeader, {
      props: { title: 'ntopng' },
      slots: {
        icon: '<svg data-test="the-icon" />',
        badge: '<span data-test="the-badge">Connected</span>',
        default: '<p data-test="more">Last seen now</p>',
        actions: '<button data-test="the-action">Docs</button>',
      },
    })
    expect(wrapper.find('.page-header__icon').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.page-header__icon [data-test="the-icon"]').exists()).toBe(true)
    expect(wrapper.find('.page-header__title [data-test="the-badge"]').text()).toBe('Connected')
    expect(wrapper.find('[data-test="more"]').text()).toBe('Last seen now')
    expect(wrapper.find('.page-header__actions [data-test="the-action"]').exists()).toBe(true)
  })

  it('leads back to the page above it', async () => {
    const { wrapper, router } = await mountWithPlugins(PageHeader, {
      props: { title: 'ntopng', back: { to: { name: 'integrations' }, label: 'All integrations' } },
    })
    const back = wrapper.find('[data-test="back"]')
    expect(back.text()).toBe('All integrations')
    expect(back.attributes('href')).toBe('/integrations')
    await back.trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('integrations')
    })
  })
})
