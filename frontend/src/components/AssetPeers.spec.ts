import AssetPeers from '@/components/AssetPeers.vue'
import { peer } from '@/test/assetDetail'
import { mountWithPlugins } from '@/test/mount'

describe('AssetPeers', () => {
  it('lists what it talked to, and what talked to it, with how often and when', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [peer(), peer({ address: '52.1.2.4', events: 1 })],
        contactedBy: [peer({ address: '192.168.1.30', events: 2 })],
      },
    })
    const talks = mounted.wrapper.findAll('[data-test="asset-talks-to"] [data-test="asset-peer"]')
    const contacts = mounted.wrapper.findAll(
      '[data-test="asset-contacted-by"] [data-test="asset-peer"]',
    )

    expect(talks.map((item) => item.text())).toEqual([
      expect.stringContaining('52.1.2.3'),
      expect.stringContaining('52.1.2.4'),
    ])
    expect(talks.at(0)?.text()).toContain('3 events')
    expect(talks.at(1)?.text()).toContain('1 event,')
    expect(contacts).toHaveLength(1)
    expect(contacts.at(0)?.text()).toContain('192.168.1.30')
    expect(contacts.at(0)?.text()).toContain('2 events')
  })

  it('says when nothing has been talked to, or talked to it, in the week', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: { talksTo: [], contactedBy: [] },
    })

    expect(mounted.wrapper.find('[data-test="asset-talks-to-none"]').exists()).toBe(true)
    expect(mounted.wrapper.find('[data-test="asset-contacted-by-none"]').exists()).toBe(true)
    expect(mounted.wrapper.find('[data-test="asset-talks-to"]').exists()).toBe(false)
  })

  it('shows the ports used at the far end, with the service each stands for', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [
          peer({
            ports: [
              { port: 443, protocol: 'tcp', events: 3 },
              { port: 40123, protocol: null, events: 1 },
            ],
          }),
          peer({ address: '52.1.2.4' }),
        ],
        contactedBy: [],
      },
    })
    const rows = mounted.wrapper.findAll('[data-test="asset-peer"]')

    expect(
      rows
        .at(0)
        ?.findAll('[data-test="peer-ports"] .v-chip')
        .map((chip) => chip.text()),
    ).toEqual(['443/tcp HTTPS', '40123'])
    expect(rows.at(1)?.find('[data-test="peer-ports"]').exists()).toBe(false)
  })

  it('says what threat intelligence kept of a peer, with the counts and the owner', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [
          peer({
            standing: {
              judgement: 'malicious',
              reported: 'malicious',
              ruling: null,
              ruling_note: null,
              malicious: 4,
              suspicious: 1,
              engines: 85,
              owner: 'Example Hosting',
              country: 'NL',
              checked_at: '2026-11-09T12:00:00Z',
            },
          }),
        ],
        contactedBy: [],
      },
    })
    const row = mounted.wrapper.find('[data-test="asset-peer"]')

    expect(row.find('[data-test="peer-standing"]').text()).toBe('Malicious')
    expect(row.find('[data-test="peer-standing"]').attributes('data-judgement')).toBe('malicious')
    expect(row.find('[data-test="peer-intel"]').text()).toBe(
      '5 of 85 engines flagged it · Example Hosting, NL',
    )
  })

  it('shows no counts for a peer with no report, and no owner when none is known', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [
          peer({
            standing: {
              judgement: 'unknown',
              reported: 'unknown',
              ruling: null,
              ruling_note: null,
              malicious: 0,
              suspicious: 0,
              engines: 0,
              owner: null,
              country: null,
              checked_at: '2026-11-09T12:00:00Z',
            },
          }),
        ],
        contactedBy: [],
      },
    })
    const row = mounted.wrapper.find('[data-test="asset-peer"]')

    expect(row.find('[data-test="peer-standing"]').text()).toBe('No report')
    expect(row.find('[data-test="peer-intel"]').exists()).toBe(false)
  })

  it('says a peer on a network of its own is on the network, and one with nothing kept is unchecked', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [peer({ address: '192.168.1.30', internal: true }), peer()],
        contactedBy: [],
      },
    })
    const rows = mounted.wrapper.findAll('[data-test="asset-peer"]')

    expect(rows.at(0)?.find('[data-test="peer-internal"]').text()).toBe('On your network')
    expect(rows.at(0)?.find('[data-test="peer-standing"]').exists()).toBe(false)
    expect(rows.at(1)?.find('[data-test="peer-unchecked"]').text()).toBe('Not checked yet')
  })

  it('shows the same for what contacted the asset: its ports, its standing and whether it is checked', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [],
        contactedBy: [
          peer({
            ports: [{ port: 3389, protocol: 'tcp', events: 2 }],
            standing: {
              judgement: 'suspicious',
              reported: 'suspicious',
              ruling: null,
              ruling_note: null,
              malicious: 0,
              suspicious: 2,
              engines: 80,
              owner: null,
              country: 'NL',
              checked_at: '2026-11-09T12:00:00Z',
            },
          }),
          peer({ address: '192.168.1.30', internal: true }),
          peer({ address: '52.1.2.4' }),
        ],
      },
    })
    const rows = mounted.wrapper.findAll(
      '[data-test="asset-contacted-by"] [data-test="asset-peer"]',
    )

    expect(rows.at(0)?.find('[data-test="peer-ports"]').text()).toBe('3389/tcp Remote Desktop')
    expect(rows.at(0)?.find('[data-test="peer-standing"]').text()).toBe('Suspicious')
    expect(rows.at(0)?.find('[data-test="peer-intel"]').text()).toBe(
      '2 of 80 engines flagged it · NL',
    )
    expect(rows.at(1)?.find('[data-test="peer-internal"]').exists()).toBe(true)
    expect(rows.at(2)?.find('[data-test="peer-unchecked"]').exists()).toBe(true)
  })

  it('says what the owner ruled of a peer, which stands over what the service said', async () => {
    const mounted = await mountWithPlugins(AssetPeers, {
      props: {
        talksTo: [
          peer({
            standing: {
              judgement: 'clean',
              reported: 'malicious',
              ruling: 'safe',
              ruling_note: 'Mine',
              malicious: 4,
              suspicious: 1,
              engines: 85,
              owner: 'Example Hosting',
              country: 'NL',
              checked_at: '2026-11-09T12:00:00Z',
            },
          }),
        ],
        contactedBy: [
          peer({
            address: '52.1.2.9',
            standing: {
              judgement: 'suspicious',
              reported: 'unknown',
              ruling: 'suspicious',
              ruling_note: null,
              malicious: 0,
              suspicious: 0,
              engines: 0,
              owner: null,
              country: null,
              checked_at: '2026-11-09T12:00:00Z',
            },
          }),
        ],
      },
    })
    const [talk] = mounted.wrapper.findAll('[data-test="asset-talks-to"] [data-test="asset-peer"]')
    const [contact] = mounted.wrapper.findAll(
      '[data-test="asset-contacted-by"] [data-test="asset-peer"]',
    )

    expect(talk?.find('[data-test="peer-standing"]').text()).toBe('Clean')
    expect(talk?.find('[data-test="peer-intel"]').text()).toBe(
      'You ruled it safe · 5 of 85 engines flagged it · Example Hosting, NL',
    )
    expect(contact?.find('[data-test="peer-standing"]').text()).toBe('Suspicious')
    expect(contact?.find('[data-test="peer-intel"]').text()).toBe('You ruled it suspicious')
  })
})
