import RecentAlerts from '@/components/RecentAlerts.vue'
import { mountWithPlugins } from '@/test/mount'
import { alert } from '@/test/dashboard'

describe('RecentAlerts', () => {
  it('lists each alert with how serious it is, what it says and who reported it', async () => {
    const { wrapper } = await mountWithPlugins(RecentAlerts, {
      props: {
        alerts: [
          alert({ id: 1, severity: 'critical', summary: 'Ransomware beacon' }),
          alert({ id: 2, severity: 'low', summary: 'Port scan', source_name: 'OPNsense' }),
        ],
      },
    })
    const items = wrapper.findAll('[data-test="recent-alert"]')
    expect(items).toHaveLength(2)
    expect(items[0]?.find('[data-test="severity"]').text()).toBe('Critical')
    expect(items[0]?.find('[data-test="alert-summary"]').text()).toBe('Ransomware beacon')
    expect(items[1]?.find('[data-test="severity"]').text()).toBe('Low')
    expect(items[1]?.find('[data-test="alert-detail"]').text()).toMatch(/^OPNsense · /)
  })

  it('says how long ago it was, and the exact time on hover', async () => {
    const { wrapper } = await mountWithPlugins(RecentAlerts, {
      props: {
        alerts: [alert({ occurred_at: new Date(Date.now() - 3 * 3_600_000).toISOString() })],
      },
    })
    const time = wrapper.find('time')
    expect(time.text()).toBe('3 hours ago')
    expect(time.attributes('title')).toMatch(/\d/)
    expect(time.attributes('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('names the addresses it is about', async () => {
    const { wrapper } = await mountWithPlugins(RecentAlerts, {
      props: {
        alerts: [
          alert({ id: 1, src_address: '198.51.100.20', dst_address: '192.168.1.20' }),
          alert({ id: 2, src_address: '203.0.113.5', dst_address: null }),
          alert({ id: 3, src_address: null, dst_address: '192.168.1.9' }),
        ],
      },
    })
    const details = wrapper.findAll('[data-test="alert-detail"]').map((item) => item.text())
    expect(details[0]).toContain('198.51.100.20 → 192.168.1.20')
    expect(details[1]).toContain('203.0.113.5')
    expect(details[1]).not.toContain('→')
    expect(details[2]).not.toContain('192.168.1.9')
  })
})
