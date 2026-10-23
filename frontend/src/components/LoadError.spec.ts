import LoadError from '@/components/LoadError.vue'
import { mountWithPlugins } from '@/test/mount'

describe('LoadError', () => {
  it('says what went wrong, as an alert', async () => {
    const { wrapper } = await mountWithPlugins(LoadError, {
      props: { message: "Can't reach AresGate." },
    })
    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.find('[data-test="load-error-message"]').text()).toBe("Can't reach AresGate.")
  })

  it('offers to try again, and says when it is trying', async () => {
    const { wrapper } = await mountWithPlugins(LoadError, { props: { message: 'No.' } })
    const retry = wrapper.find('[data-test="retry"]')
    expect(retry.text()).toBe('Try again')
    await retry.trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)

    await wrapper.setProps({ loading: true })
    expect(wrapper.find('[data-test="retry"]').classes()).toContain('v-btn--loading')
  })

  it('names its button, so a page with several can tell them apart', async () => {
    const { wrapper } = await mountWithPlugins(LoadError, {
      props: { message: 'No.', retryTestId: 'log-retry' },
    })
    expect(wrapper.find('[data-test="log-retry"]').exists()).toBe(true)
  })

  it('has no button for a failure that asking again would not change', async () => {
    const { wrapper } = await mountWithPlugins(LoadError, {
      props: { message: 'There is no such page.', canRetry: false },
    })
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(false)
  })
})
