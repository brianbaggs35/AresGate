import type { Status } from '@/api/integrations'
import StatusChip from '@/components/StatusChip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('StatusChip', () => {
  it.each<[Status, string]>([
    ['not_connected', 'Not connected'],
    ['untested', 'Not tested yet'],
    ['connected', 'Connected'],
    ['problem', 'Problem'],
  ])('says %s in words', async (status, words) => {
    const { wrapper } = await mountWithPlugins(StatusChip, { props: { status } })
    expect(wrapper.find('[data-test="status"]').text()).toBe(words)
  })
})
