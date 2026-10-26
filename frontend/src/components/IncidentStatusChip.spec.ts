import type { IncidentStatus } from '@/api/incidents'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('IncidentStatusChip', () => {
  it.each<[IncidentStatus, string]>([
    ['open', 'Open'],
    ['investigating', 'Investigating'],
    ['resolved', 'Resolved'],
    ['dismissed', 'Dismissed'],
  ])('says %s in words', async (status, words) => {
    const { wrapper } = await mountWithPlugins(IncidentStatusChip, { props: { status } })
    expect(wrapper.find('[data-test="incident-status"]').text()).toBe(words)
  })
})
