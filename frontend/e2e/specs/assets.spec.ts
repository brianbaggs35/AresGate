import type { AssetDeviceRequest, AssetHostRequest } from '../support'
import { connectFirewall, expect, test } from '../support'

const LAPTOP = '00:11:22:0a:0b:0c'
const PHONE = '02:aa:bb:cc:dd:ee'

/** Four devices: a laptop that is on and that two programs list, a phone with a private address
 * and a lease only, a camera that has been gone for days, and one that says nothing of itself. */
const DEVICES: AssetDeviceRequest[] = [
  {
    hostname: 'laptop',
    mac: LAPTOP,
    vendor: 'Example Devices Inc.',
    addresses: ['192.168.1.20'],
    listed: [
      { source: 'opnsense', via: 'arp', minutes_ago: 1 },
      { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
    ],
  },
  {
    hostname: 'phone',
    mac: PHONE,
    addresses: ['192.168.1.9'],
    listed: [{ source: 'opnsense', via: 'dhcp', minutes_ago: 30 }],
    first_seen_hours: 30,
  },
  {
    hostname: 'camera',
    vendor: 'Example Cameras Corp.',
    addresses: ['192.168.20.40'],
    listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 3 * 24 * 60 }],
    first_seen_hours: 24 * 50,
  },
  { mac: '00:11:22:0a:0b:0e', listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 120 }] },
]

/** An agent that has the laptop's name and address, and one that is nothing else in the list. */
const HOSTS: AssetHostRequest[] = [
  { key: '002', hostname: 'laptop', address: '192.168.1.20', minutes_ago: 2 },
  { key: '003', hostname: 'build-server', address: '192.168.1.50', minutes_ago: 5 },
]

test.describe('assets', () => {
  test('is in the menu, and has a title of its own', async ({ page, shell, assets }) => {
    await page.goto('/')

    await shell.goTo('assets')

    await expect(page).toHaveURL('/assets')
    await expect(page).toHaveTitle('Assets · AresGate')
    await shell.expectCurrent('assets')
    await expect(assets.heading).toHaveText('Assets')
  })

  test.describe('with nothing connected', () => {
    test('says that devices appear once a program that lists them is connected', async ({
      assets,
      page,
    }) => {
      await assets.goto()

      await expect(assets.emptyTitle).toHaveText('No devices yet')
      await expect(assets.empty).toContainText('ARP table and DHCP leases')
      await expect(assets.cards).toHaveCount(0)
      // The programs that could list them are there to be set up.
      await expect(assets.supplier('opnsense')).toContainText('Not connected')

      await assets.empty.getByTestId('empty-integrations').click()

      await expect(page).toHaveURL('/integrations')
    })
  })

  test.describe('with a firewall connected that has listed nothing yet', () => {
    test('says it is waiting, and leads to the Status page', async ({
      harness,
      integration,
      assets,
      page,
    }) => {
      await connectFirewall(harness, integration, ['arp'])
      await assets.goto()

      await expect(assets.emptyTitle).toHaveText('Waiting for the first devices')
      await expect(assets.empty).toContainText('OPNsense is connected')
      await expect(assets.supplier('opnsense')).toContainText('Connected')

      await assets.empty.getByTestId('empty-status').click()

      await expect(page).toHaveURL('/status')
    })
  })

  test.describe('with a firewall that has been read', () => {
    test('lists what its ARP table holds, as the collectors left it', async ({
      harness,
      integration,
      assets,
    }) => {
      await connectFirewall(harness, integration, [])
      await harness.setWorker('running')
      await harness.runCollectors()

      await assets.goto()

      // The laptop of the stand-in's ARP table, which has a maker and no name.
      const laptop = assets.card('Example Devices Inc.')
      await expect(laptop).toContainText('00:11:22:0a:0b:0c')
      await expect(laptop).toContainText('192.168.1.20')
      await expect(laptop.getByTestId('asset-source-opnsense')).toContainText('ARP table')
      await expect(laptop.getByTestId('asset-status')).toHaveText('Online')
      await expect(assets.supplier('opnsense')).toContainText('Connected')
      await expect(assets.empty).toHaveCount(0)
    })
  })

  test.describe('with devices', () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createAssets({ devices: DEVICES, hosts: HOSTS })
    })

    test('lists each once, the ones listed most recently first, with how many are on', async ({
      assets,
    }) => {
      await assets.goto()

      await expect(assets.cards).toHaveCount(5)
      await expect(assets.names).toHaveText([
        'laptop',
        'build-server',
        'phone',
        '00:11:22:0a:0b:0e',
        'camera',
      ])
      await expect(assets.description).toHaveText('5 assets, 2 online now.')
      await expect(assets.count('all')).toHaveText('5')
      await expect(assets.count('online')).toHaveText('2')
      await expect(assets.count('recent')).toHaveText('2')
      await expect(assets.count('away')).toHaveText('1')
    })

    test('puts together what the programs say about a device, and names who listed it', async ({
      assets,
    }) => {
      await assets.goto()

      const laptop = assets.card('laptop')
      await expect(laptop).toContainText('Example Devices Inc.')
      await expect(laptop).toContainText(LAPTOP)
      await expect(laptop).toContainText('192.168.1.20')
      await expect(laptop.getByTestId('asset-status')).toHaveText('Online')
      // OPNsense by the ARP table, ntopng by its hosts and Wazuh by an agent matched to it.
      await expect(laptop.getByTestId('asset-source-opnsense')).toContainText('ARP table')
      await expect(laptop.getByTestId('asset-source-ntopng')).toContainText('Active hosts')
      await expect(laptop.getByTestId('asset-source-wazuh')).toContainText(
        'Agent (matched by address)',
      )
    })

    test('lists a machine no device matches as an asset of its own', async ({ assets }) => {
      await assets.goto()

      const machine = assets.card('build-server')
      await expect(machine).toContainText('Wazuh agent · active')
      await expect(machine).toContainText('192.168.1.50')
      await expect(machine.getByTestId('asset-status')).toHaveText('Online')
    })

    test('says in words, not only in color, whether each is there', async ({ assets }) => {
      await assets.goto()

      await expect(assets.card('laptop').getByTestId('asset-status')).toHaveText('Online')
      await expect(assets.card('phone').getByTestId('asset-status')).toHaveText('Seen recently')
      await expect(assets.card('camera').getByTestId('asset-status')).toHaveText(
        'Not seen for a while',
      )
    })

    test('flags a device that is new, one that made up its hardware address and one that says nothing of itself', async ({
      assets,
    }) => {
      await assets.goto()

      await expect(assets.card('phone').getByTestId('asset-new')).toHaveText('New this week')
      await expect(assets.card('phone').getByTestId('asset-private')).toBeVisible()
      await expect(assets.card('00:11:22:0a:0b:0e').getByTestId('asset-unidentified')).toBeVisible()
      await expect(assets.card('laptop').getByTestId('asset-new')).toHaveCount(0)
    })

    test('narrows to a state, and says so in the address, so a link brings it back', async ({
      assets,
      page,
    }) => {
      await assets.goto()

      await assets.view('away').click()

      await expect(page).toHaveURL('/assets?status=away')
      await expect(assets.names).toHaveText(['camera'])
      await expect(assets.view('away')).toHaveAttribute('aria-pressed', 'true')

      await page.reload()

      await expect(assets.names).toHaveText(['camera'])
      await assets.view('all').click()
      await expect(assets.cards).toHaveCount(5)
      await expect(page).toHaveURL('/assets')
    })

    test('searches by name, address, maker and hardware address, and by the program that lists it', async ({
      assets,
      page,
    }) => {
      await assets.goto()

      await assets.find('camera')
      await expect(assets.names).toHaveText(['camera'])
      await expect(page).toHaveURL('/assets?q=camera')

      await assets.find('192.168.1.9')
      await expect(assets.names).toHaveText(['phone'])

      await assets.find('00-11-22-0a-0b-0c')
      await expect(assets.names).toHaveText(['laptop'])

      await assets.find('example cameras')
      await expect(assets.names).toHaveText(['camera'])

      await assets.find('ntopng')
      await expect(assets.names).toHaveText(['laptop'])
    })

    test('is searched from anywhere with the slash key', async ({ assets, page }) => {
      await assets.goto()
      await expect(assets.cards).toHaveCount(5)

      await page.keyboard.press('/')

      await expect(assets.search).toBeFocused()
    })

    test('narrows to what one program lists', async ({ assets }) => {
      await assets.goto()

      await assets.source('wazuh').click()

      await expect(assets.source('wazuh')).toHaveAttribute('aria-pressed', 'true')
      await expect(assets.names).toHaveText(['laptop', 'build-server'])
    })

    test('narrows to what is new, and to what says nothing of itself', async ({ assets }) => {
      await assets.goto()

      // The agent that no device matched was listed for the first time minutes ago.
      await assets.newOnly.click()
      await expect(assets.newOnly).toHaveAttribute('aria-pressed', 'true')
      await expect(assets.names).toHaveText(['build-server', 'phone'])

      await assets.newOnly.click()
      await assets.unidentified.click()
      await expect(assets.names).toHaveText(['00:11:22:0a:0b:0e'])
    })

    test('orders by name, and clears the choices without losing the order', async ({
      assets,
      page,
    }) => {
      await assets.goto('?sort=name&q=o')

      await expect(assets.clear).toBeVisible()
      await assets.clear.click()

      await expect(page).toHaveURL('/assets?sort=name')
      await expect(assets.names.first()).toHaveText('00:11:22:0a:0b:0e')
      await expect(assets.clear).toHaveCount(0)
    })

    test('says nothing matches when nothing does, and offers to clear the search', async ({
      assets,
    }) => {
      await assets.goto()

      await assets.find('no such device')

      await expect(assets.emptyTitle).toHaveText('Nothing matches')
      await assets.empty.getByTestId('empty-clear').click()
      await expect(assets.cards).toHaveCount(5)
    })

    test('says where the assets come from, and how many each lists', async ({ assets }) => {
      await assets.goto()

      await expect(assets.supplier('opnsense')).toContainText(
        'lists ARP table and DHCL leases'.replace('DHCL', 'DHCP'),
      )
      await expect(assets.supplier('opnsense')).toContainText('4 assets')
      await expect(assets.supplier('ntopng')).toContainText('1 asset')
      await expect(assets.note).toContainText('New means first listed in the last 7 days')
    })

    test('asks again for what is shown when told to', async ({ assets, harness }) => {
      await assets.goto()
      await expect(assets.cards).toHaveCount(5)
      await harness.createAssets({
        devices: [{ hostname: 'tv', mac: '00:11:22:0a:0b:ff', addresses: ['192.168.1.77'] }],
      })

      await assets.refresh.click()

      await expect(assets.cards).toHaveCount(6)
    })
  })

  test('offers more when there are more than a page', async ({ harness, assets }) => {
    await harness.createAssets({
      devices: Array.from({ length: 35 }, (_, number) => ({
        hostname: `device-${String(number).padStart(2, '0')}`,
        addresses: [`192.168.1.${number + 10}`],
      })),
    })
    await assets.goto('?sort=name')

    await expect(assets.cards).toHaveCount(30)
    await expect(assets.showMore).toHaveText('Show 5 more')

    await assets.showMore.click()

    await expect(assets.cards).toHaveCount(35)
    await expect(assets.showMore).toHaveCount(0)
  })
})
