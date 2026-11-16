import HealthStrip from '@/components/HealthStrip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('HealthStrip', () => {
  it('has a cell for each hour, oldest first, and says in words how they went', async () => {
    const { wrapper } = await mountWithPlugins(HealthStrip, {
      props: { states: ['ok', 'problem', 'none'], name: 'Wazuh' },
    })

    expect(
      wrapper.findAll('[data-test="health-cell"]').map((cell) => cell.attributes('data-state')),
    ).toEqual(['ok', 'problem', 'none'])
    expect(
      wrapper.findAll('[data-test="health-cell"]').map((cell) => cell.attributes('title')),
    ).toEqual(['Working', 'Problem', 'No calls'])
    expect(wrapper.find('[data-test="health-summary"]').text()).toBe(
      'In the last 3 hours: 1 hour working, 1 with a problem.',
    )
    expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe(
      'Wazuh. In the last 3 hours: 1 hour working, 1 with a problem.',
    )
  })
})
