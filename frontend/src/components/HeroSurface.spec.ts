import { Siren } from '@lucide/vue'

import HeroSurface from '@/components/HeroSurface.vue'
import { mountWithPlugins } from '@/test/mount'

const props = { testId: 'hero', tone: 'warning', eyebrow: 'Keep an eye on it', title: 'A title' }

describe('HeroSurface', () => {
  it('says its eyebrow, its title and its detail, each for a test to find', async () => {
    const { wrapper } = await mountWithPlugins(HeroSurface, {
      props: { ...props, detail: 'A detail.' },
    })

    expect(wrapper.find('[data-test="hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="hero-eyebrow"]').text()).toBe('Keep an eye on it')
    expect(wrapper.find('[data-test="hero-title"]').text()).toBe('A title')
    expect(wrapper.find('[data-test="hero-detail"]').text()).toBe('A detail.')
    expect(wrapper.find('output').text()).toContain('A title')
  })

  it('leaves out the detail when there is none', async () => {
    const { wrapper } = await mountWithPlugins(HeroSurface, { props })

    expect(wrapper.find('[data-test="hero-detail"]').exists()).toBe(false)
  })

  it('takes its color from the theme color it is given', async () => {
    const { wrapper } = await mountWithPlugins(HeroSurface, { props })

    expect(wrapper.find('[data-test="hero"]').attributes('style')).toContain('--v-theme-warning')
  })

  it('is calm unless it is told its mood', async () => {
    const calm = await mountWithPlugins(HeroSurface, { props })
    const urgent = await mountWithPlugins(HeroSurface, { props: { ...props, mood: 'urgent' } })

    expect(calm.wrapper.find('[data-test="hero"]').attributes('data-mood')).toBe('calm')
    expect(urgent.wrapper.find('[data-test="hero"]').attributes('data-mood')).toBe('urgent')
  })

  it('draws a whole ring unless it is told how much', async () => {
    const whole = await mountWithPlugins(HeroSurface, { props })
    const part = await mountWithPlugins(HeroSurface, { props: { ...props, level: 70 } })

    expect(whole.wrapper.find('.hero__arc').attributes('style')).toContain('stroke-dashoffset: 0')
    expect(part.wrapper.find('.hero__arc').attributes('style')).toContain('stroke-dashoffset: 30')
  })

  it('puts an icon in the ring, or whatever the center is given instead', async () => {
    const icon = await mountWithPlugins(HeroSurface, { props: { ...props, icon: Siren } })
    const centered = await mountWithPlugins(HeroSurface, {
      props: { ...props, icon: Siren },
      slots: { center: '<b data-test="score">70</b>' },
    })
    const empty = await mountWithPlugins(HeroSurface, { props })

    expect(icon.wrapper.find('.hero__ring .v-icon').exists()).toBe(true)
    expect(centered.wrapper.find('.hero__ring [data-test="score"]').text()).toBe('70')
    expect(centered.wrapper.find('.hero__ring .v-icon').exists()).toBe(false)
    expect(empty.wrapper.find('.hero__ring .v-icon').exists()).toBe(false)
  })

  it('keeps the ring and the glow out of what a screen reader hears', async () => {
    const { wrapper } = await mountWithPlugins(HeroSurface, { props })

    expect(wrapper.find('.hero__backdrop').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.hero__ring').attributes('aria-hidden')).toBe('true')
  })

  it('has a place for an action and for the numbers, only when they are given', async () => {
    const bare = await mountWithPlugins(HeroSurface, { props })
    const full = await mountWithPlugins(HeroSurface, {
      props,
      slots: { action: '<a data-test="go">Go</a>', default: '<p data-test="vital">32</p>' },
    })

    expect(bare.wrapper.find('.hero__action').exists()).toBe(false)
    expect(bare.wrapper.find('.hero__vitals').exists()).toBe(false)
    expect(full.wrapper.find('.hero__action [data-test="go"]').exists()).toBe(true)
    expect(full.wrapper.find('.hero__vitals [data-test="vital"]').text()).toBe('32')
  })
})
