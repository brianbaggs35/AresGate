import IncidentLayoutToggle from '@/components/IncidentLayoutToggle.vue'
import { useIncidentLayoutStore } from '@/stores/incident-layout'
import { mountWithPlugins } from '@/test/mount'

describe('IncidentLayoutToggle', () => {
  it('shows cards as the choice, with a name for each button and no grouping yet', async () => {
    const { wrapper } = await mountWithPlugins(IncidentLayoutToggle, { withApp: true })

    expect(wrapper.find('[data-test="layout"]').attributes('aria-label')).toBe('Layout')
    expect(wrapper.find('[data-test="layout-cards"]').attributes('aria-label')).toBe('Cards')
    expect(wrapper.find('[data-test="layout-cards"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-test="layout-table"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.find('[data-test="group-by-address"]').exists()).toBe(false)
  })

  it('chooses the table, and the cards again', async () => {
    const { wrapper, pinia } = await mountWithPlugins(IncidentLayoutToggle, { withApp: true })
    const layout = useIncidentLayoutStore(pinia)

    await wrapper.find('[data-test="layout-table"]').trigger('click')
    expect(layout.layout).toBe('table')

    await wrapper.find('[data-test="layout-cards"]').trigger('click')
    expect(layout.layout).toBe('cards')
  })

  it('offers grouping by address for the table, which is switched on and off', async () => {
    const { wrapper, pinia } = await mountWithPlugins(IncidentLayoutToggle, { withApp: true })
    const layout = useIncidentLayoutStore(pinia)
    await wrapper.find('[data-test="layout-table"]').trigger('click')
    const group = () => wrapper.find('[data-test="group-by-address"]')

    expect(group().attributes('aria-pressed')).toBe('false')

    await group().trigger('click')
    expect(layout.grouping).toBe('address')
    expect(group().attributes('aria-pressed')).toBe('true')

    await group().trigger('click')
    expect(layout.grouping).toBe('none')
  })
})
