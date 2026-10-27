import * as api from '@/api/logs'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { logEvent, logEvents, logPage } from '@/test/logs'
import LogsView from '@/views/LogsView.vue'

// A page that is live keeps only so many events, which is far more than a test wants to draw.
vi.mock('@/logs', async (original) => ({
  ...(await original<typeof import('@/logs')>()),
  MAX_ROWS: 3,
}))

describe('LogsView, kept to so many events', () => {
  it('drops the oldest ones as new ones arrive, and offers to bring them back', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const fetchLogs = vi.spyOn(api, 'fetchLogs').mockResolvedValue(logPage(logEvents(3)))
      const { wrapper } = await mountWithPlugins(LogsView, {
        signedIn: 'admin',
        withApp: true,
        route: '/logs',
        width: 1280,
      })
      await flushPromises()
      expect(wrapper.find('[data-test="more"]').exists()).toBe(false)

      fetchLogs.mockResolvedValue(
        logPage([logEvent({ id: 9, at: new Date().toISOString(), summary: 'Newest' })], {
          summary: null,
        }),
      )
      vi.advanceTimersByTime(5000)
      await flushPromises()

      const summaries = wrapper.findAll('[data-test="log-open"]').map((row) => row.text())
      expect(summaries).toEqual([
        'Newest',
        'Blocked connection number 3',
        'Blocked connection number 2',
      ])
      expect(wrapper.find('[data-test="show-older"]').exists()).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
