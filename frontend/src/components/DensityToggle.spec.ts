import DensityToggle from '@/components/DensityToggle.vue'
import { useDensityStore } from '@/stores/density'
import { mountWithPlugins } from '@/test/mount'

describe('DensityToggle', () => {
  it('shows the choice that is made, with a name for each button', async () => {
    const { wrapper } = await mountWithPlugins(DensityToggle, { withApp: true })

    expect(wrapper.find('[data-test="density"]').attributes('aria-label')).toBe('Density')
    expect(wrapper.find('[data-test="density-comfortable"]').attributes('aria-label')).toBe(
      'Comfortable',
    )
    expect(wrapper.find('[data-test="density-comfortable"]').classes()).toContain('v-btn--active')
    expect(wrapper.find('[data-test="density-compact"]').classes()).not.toContain('v-btn--active')
  })

  it('makes the list compact, and roomy again', async () => {
    const { wrapper, pinia } = await mountWithPlugins(DensityToggle, { withApp: true })
    const density = useDensityStore(pinia)

    await wrapper.find('[data-test="density-compact"]').trigger('click')
    expect(density.preference).toBe('compact')

    await wrapper.find('[data-test="density-comfortable"]').trigger('click')
    expect(density.preference).toBe('comfortable')
  })
})
