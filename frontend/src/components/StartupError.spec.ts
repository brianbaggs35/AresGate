import StartupError from '@/components/StartupError.vue'
import { mountWithPlugins } from '@/test/mount'

describe('StartupError', () => {
  it('says what went wrong, as an alert', async () => {
    const { wrapper } = await mountWithPlugins(StartupError, {
      props: { message: "Can't reach AresGate.", busy: false },
    })
    expect(wrapper.find('[role="alert"]').text()).toBe("Can't reach AresGate.")
  })

  it('offers to try again', async () => {
    const { wrapper } = await mountWithPlugins(StartupError, {
      props: { message: 'x', busy: false },
    })
    await wrapper.find('[data-test="retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('shows that it is trying', async () => {
    const { wrapper } = await mountWithPlugins(StartupError, {
      props: { message: 'x', busy: true },
    })
    expect(wrapper.find('[data-test="retry"]').classes()).toContain('v-btn--loading')
  })
})
