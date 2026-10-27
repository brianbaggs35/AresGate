import StatusHero from '@/components/StatusHero.vue'
import type { PostureState } from '@/dashboard'
import { mountWithPlugins } from '@/test/mount'

const posture = (state: PostureState) => ({
  state,
  title: `Title ${state}`,
  detail: `Detail ${state}`,
})

describe('StatusHero', () => {
  it.each([
    ['attention', 'error', 'Needs you'],
    ['watch', 'warning', 'Keep an eye on it'],
    ['calm', 'success', 'All clear'],
    ['setup', 'info', 'Set up'],
  ] as const)(
    'says what a %s state is in words, with its own look',
    async (state, color, label) => {
      const { wrapper } = await mountWithPlugins(StatusHero, {
        props: { posture: posture(state) },
      })
      const hero = wrapper.find('[data-test="posture"]')
      expect(hero.attributes('data-state')).toBe(state)
      expect(hero.find('output').exists()).toBe(true)
      expect(hero.attributes('style')).toContain(`--v-theme-${color}`)
      expect(wrapper.find('[data-test="posture-eyebrow"]').text()).toBe(label)
      expect(wrapper.find('[data-test="posture-title"]').text()).toBe(`Title ${state}`)
      expect(wrapper.find('[data-test="posture-detail"]').text()).toBe(`Detail ${state}`)
      expect(hero.find('.v-icon').exists()).toBe(true)
    },
  )

  it('keeps the ring and the glow out of what a screen reader hears', async () => {
    const { wrapper } = await mountWithPlugins(StatusHero, { props: { posture: posture('calm') } })

    expect(wrapper.find('.hero__backdrop').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.hero__ring').attributes('aria-hidden')).toBe('true')
  })

  it('has no button unless there is somewhere to go', async () => {
    const { wrapper } = await mountWithPlugins(StatusHero, { props: { posture: posture('calm') } })

    expect(wrapper.find('[data-test="posture-action"]').exists()).toBe(false)
  })

  it('leads on to where it says', async () => {
    const { wrapper } = await mountWithPlugins(StatusHero, {
      props: {
        posture: posture('setup'),
        action: { label: 'Connect an integration', to: { name: 'integrations' } },
      },
    })

    const action = wrapper.find('[data-test="posture-action"]')
    expect(action.text()).toBe('Connect an integration')
    expect(action.attributes('href')).toBe('/integrations')
  })

  it('shows the numbers that back it up underneath, when it is given some', async () => {
    const { wrapper } = await mountWithPlugins(StatusHero, {
      props: { posture: posture('calm') },
      slots: { default: '<p data-test="vital">32 alerts</p>' },
    })

    expect(wrapper.find('.hero__vitals [data-test="vital"]').text()).toBe('32 alerts')
  })

  it('has no strip for numbers when it is given none', async () => {
    const { wrapper } = await mountWithPlugins(StatusHero, { props: { posture: posture('calm') } })

    expect(wrapper.find('.hero__vitals').exists()).toBe(false)
  })
})
