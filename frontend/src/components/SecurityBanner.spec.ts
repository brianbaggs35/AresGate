import SecurityBanner from '@/components/SecurityBanner.vue'
import type { PostureState } from '@/dashboard'
import { mountWithPlugins } from '@/test/mount'

const posture = (state: PostureState) => ({
  state,
  title: `Title ${state}`,
  detail: `Detail ${state}`,
})

describe('SecurityBanner', () => {
  it.each([
    ['attention', 'error'],
    ['watch', 'warning'],
    ['calm', 'success'],
    ['setup', 'info'],
  ] as const)('says what a %s state is in words, with its own look', async (state, color) => {
    const { wrapper } = await mountWithPlugins(SecurityBanner, {
      props: { posture: posture(state) },
    })
    const banner = wrapper.find('[data-test="posture"]')
    expect(banner.attributes('data-state')).toBe(state)
    expect(banner.find('[role="status"]').exists()).toBe(true)
    expect(banner.attributes('style')).toContain(`--v-theme-${color}`)
    expect(wrapper.find('[data-test="posture-title"]').text()).toBe(`Title ${state}`)
    expect(wrapper.find('[data-test="posture-detail"]').text()).toBe(`Detail ${state}`)
    expect(banner.find('.v-icon').exists()).toBe(true)
  })

  it('has no button unless there is somewhere to go', async () => {
    const { wrapper } = await mountWithPlugins(SecurityBanner, {
      props: { posture: posture('calm') },
    })
    expect(wrapper.find('[data-test="posture-action"]').exists()).toBe(false)
  })

  it('leads on to where it says', async () => {
    const { wrapper } = await mountWithPlugins(SecurityBanner, {
      props: {
        posture: posture('setup'),
        action: { label: 'Connect an integration', to: { name: 'integrations' } },
      },
    })
    const action = wrapper.find('[data-test="posture-action"]')
    expect(action.text()).toBe('Connect an integration')
    expect(action.attributes('href')).toBe('/integrations')
  })
})
