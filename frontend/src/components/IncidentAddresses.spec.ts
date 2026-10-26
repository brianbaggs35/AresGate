import IncidentAddresses from '@/components/IncidentAddresses.vue'
import { device } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(IncidentAddresses, {
    props: {
      subject: '93.184.216.34',
      addresses: ['93.184.216.34', '192.168.1.20'],
      devices: [device()],
      ...props,
    },
  })
  const rows = () => mounted.wrapper.findAll('[data-test="address"]')
  return { ...mounted, rows }
}

describe('IncidentAddresses', () => {
  it('lists the addresses, the one it is about first and marked', async () => {
    const { rows } = await show()

    expect(rows().map((row) => row.find('[data-test="address-value"]').text())).toEqual([
      '93.184.216.34',
      '192.168.1.20',
    ])
    expect(rows()[0]?.find('[data-test="address-subject"]').text()).toBe('What it is about')
    expect(rows()[1]?.find('[data-test="address-subject"]').exists()).toBe(false)
  })

  it('names the device behind an address, with what is known of it', async () => {
    const { rows } = await show()

    const found = rows()[1]?.find('[data-test="address-device"]').text()
    expect(found).toContain('nas')
    expect(found).toContain('On your network')
    expect(found).toContain('Synology')
    expect(found).toContain('aa:bb:cc:00:11:22')
  })

  it('says an address that no device has is somewhere else', async () => {
    const { rows } = await show()

    expect(rows()[0]?.find('[data-test="address-elsewhere"]').text()).toBe(
      'Not a device AresGate knows.',
    )
  })

  it('says a device with no name has none, and leaves out a maker it does not know', async () => {
    const { rows } = await show({ devices: [device({ hostname: null, vendor: null })] })

    const found = rows()[1]?.find('[data-test="address-device"]').text()
    expect(found).toContain('A device with no name')
    expect(found).not.toContain('·  ·')
    expect(found).not.toContain('Synology')
  })

  it('says what the rule was for an incident that is about one', async () => {
    const { wrapper, rows } = await show({
      subject: 'rule:wazuh:sshd: authentication failed',
      addresses: [],
      devices: [],
    })

    expect(rows()).toHaveLength(0)
    expect(wrapper.find('[data-test="addresses-rule"]').text()).toContain(
      'sshd: authentication failed',
    )
    expect(wrapper.text()).not.toContain('No addresses were named.')
  })

  it('says when there are no addresses and no rule', async () => {
    const { wrapper } = await show({ subject: '', addresses: [], devices: [] })

    expect(wrapper.text()).toContain('No addresses were named.')
  })
})
