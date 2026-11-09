import type {
  AssetDeviceRequest,
  AssetPage,
  AssetsPage,
  EventRequest,
  IncidentRequest,
  VerdictRequest,
} from '../support'
import { expect, test } from '../support'

const LAPTOP = '00:11:22:0a:0b:0c'
const ADDRESS = '192.168.1.20'
const EARLIER = '192.168.1.19'
const SERVER = '52.1.2.3'
const VISITOR = '52.1.2.4'
const ATTACKER = '93.184.216.34'

/** A laptop that two programs list, at the address it has now and one it had before. */
const LAPTOP_DEVICE: AssetDeviceRequest = {
  hostname: 'laptop',
  mac: LAPTOP,
  vendor: 'Example Devices Inc.',
  addresses: [ADDRESS],
  earlier: [EARLIER],
  listed: [
    { source: 'opnsense', via: 'arp', minutes_ago: 1 },
    { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
  ],
}

/** The laptop tried to reach a server that the firewall blocked, and a visitor tried to log in. */
const EVENTS: EventRequest[] = [
  {
    source: 'opnsense',
    kind: 'firewall',
    severity: 'info',
    summary: `Blocked tcp from ${ADDRESS} to ${SERVER}`,
    src_address: ADDRESS,
    src_port: 51234,
    dst_address: SERVER,
    dst_port: 443,
    protocol: 'tcp',
    seconds_ago: 60,
  },
  {
    source: 'wazuh',
    kind: 'alert',
    severity: 'high',
    summary: 'sshd: Failed password for root',
    signature: 'Attempt to login using a non-existent user',
    src_address: VISITOR,
    dst_address: ADDRESS,
    dst_port: 22,
    protocol: 'tcp',
    seconds_ago: 120,
  },
]

/** What ntopng read of the laptop, an hour apart. Its counters rose by 9000 bytes sent over the
 * day (8.8 KB) and by 400 received. */
const TRAFFIC = [{ host: ADDRESS, sent: [1000, 3000, 6000, 10000], received: [500, 600, 700, 900] }]

/** A verdict that a port scan from the laptop to a network is a real threat. */
const VERDICT: VerdictRequest = {
  verdict: 'threat',
  address: ADDRESS,
  destination: '52.1.2.0/24',
  signature: 'Port scan',
}

/** An attack that two programs saw, on the laptop, which is the device it attacks by default. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 5,
}

/** Opens the laptop's page from the list of assets, as someone would. */
async function openLaptop(assets: AssetsPage, asset: AssetPage): Promise<void> {
  await assets.goto()
  await assets.open('laptop')
  await expect(asset.heading).toHaveText('laptop')
}

test.describe('an asset', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createAssets({ devices: [LAPTOP_DEVICE] })
  })

  test('is opened from its name on the list, and goes back to the list', async ({
    assets,
    asset,
    page,
  }) => {
    await assets.goto()

    await assets.open('laptop')

    await expect(page).toHaveURL(/\/assets\/device-\d+$/)
    await expect(asset.heading).toHaveText('laptop')
    await asset.back.click()
    await expect(page).toHaveURL('/assets')
  })

  test('says what it is, and whether it is there now', async ({ assets, asset }) => {
    await openLaptop(assets, asset)

    await expect(asset.description).toHaveText('Device · Example Devices Inc. · 00:11:22:0a:0b:0c')
    await expect(asset.status).toHaveText('Online')
    await expect(asset.listedTile).toContainText('Online')
  })

  test('lists its addresses, and says which of them it has now', async ({ assets, asset }) => {
    await openLaptop(assets, asset)

    await expect(asset.addresses).toHaveCount(2)
    await expect(asset.addresses.filter({ hasText: ADDRESS })).toContainText('Now')
    await expect(asset.addresses.filter({ hasText: EARLIER })).toContainText('Before')
  })

  test('says which programs list it, and how each one does', async ({ assets, asset }) => {
    await openLaptop(assets, asset)

    await expect(asset.listedBy.getByTestId('asset-source-opnsense')).toContainText('ARP table')
    await expect(asset.listedBy.getByTestId('asset-source-ntopng')).toContainText('Active hosts')
  })

  test('charts the traffic ntopng measured, and totals it for the day', async ({
    assets,
    asset,
    harness,
  }) => {
    await harness.createTraffic(TRAFFIC)

    await openLaptop(assets, asset)

    await expect(asset.sentTile).toContainText('8.8 KB')
    await expect(asset.receivedTile).toContainText('400 B')
    await expect(asset.chart).toBeVisible()
    await expect(asset.window('24 hours')).toHaveAttribute('aria-pressed', 'true')

    await asset.window('7 days').click()

    await expect(asset.window('7 days')).toHaveAttribute('aria-pressed', 'true')
    await expect(asset.chart).toBeVisible()
  })

  test('lists the events its addresses were in, newest first, and how many there were in the week', async ({
    assets,
    asset,
    harness,
  }) => {
    await harness.createEvents(EVENTS)

    await openLaptop(assets, asset)

    await expect(asset.eventsNote).toHaveText('2 in the last week, newest first.')
    await expect(asset.eventItems).toHaveCount(2)
    await expect(asset.eventItems.first()).toContainText('OPNsense')
    await expect(asset.eventFlows.first()).toContainText(`To ${SERVER}:443`)
    await expect(asset.eventItems.last()).toContainText('Wazuh')
    await expect(asset.eventFlows.last()).toContainText(`From ${VISITOR}`)
  })

  test('shows what it talked to, and what talked to it, in the week', async ({
    assets,
    asset,
    harness,
  }) => {
    await harness.createEvents(EVENTS)

    await openLaptop(assets, asset)

    await expect(asset.peers).toHaveCount(2)
    await expect(asset.talksTo).toContainText(SERVER)
    await expect(asset.talksTo).toContainText('1 event')
    await expect(asset.contactedBy).toContainText(VISITOR)
  })

  test('lists the incidents its addresses are in, and each one opens its own page', async ({
    assets,
    asset,
    harness,
    page,
  }) => {
    await harness.createIncidents([ATTACK])

    await openLaptop(assets, asset)

    await expect(asset.incidents).toHaveCount(1)
    await expect(asset.incidents.first()).toContainText(ATTACKER)
    await asset.incidents.first().click()
    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('lists the verdicts given about it, with what each one is about', async ({
    assets,
    asset,
    harness,
  }) => {
    await harness.createVerdicts([VERDICT])

    await openLaptop(assets, asset)

    await expect(asset.verdicts).toHaveCount(1)
    await expect(asset.verdicts.first()).toContainText('Real threat')
    await expect(asset.verdicts.first()).toContainText(
      'its traffic to 52.1.2.0/24 and the alert "Port scan"',
    )
  })

  test('says what is not known yet, rather than making it up', async ({ assets, asset }) => {
    await openLaptop(assets, asset)

    await expect(asset.sentTile).toContainText('Nothing measured yet')
    await expect(asset.eventsNote).toHaveText('Nothing in the last week.')
    await expect(asset.talksToNone).toBeVisible()
    await expect(asset.contactedByNone).toBeVisible()
    await expect(asset.noIncidents).toBeVisible()
    await expect(asset.noVerdicts).toBeVisible()
  })

  test('says the asset is not there when it is not on the list', async ({ asset }) => {
    await asset.goto('device-999999')

    await expect(asset.missing).toBeVisible()
    await expect(asset.missing).toContainText("That asset isn't there")
  })

  test('shows what went wrong when it cannot be read, and asks again', async ({
    assets,
    asset,
    page,
  }) => {
    await openLaptop(assets, asset)
    await page.route('**/api/assets/**', (route) => route.abort())

    await page.reload()

    await expect(asset.failure).toBeVisible()
    await page.unroute('**/api/assets/**')
    await asset.retry.click()

    await expect(asset.heading).toHaveText('laptop')
    await expect(asset.failure).toHaveCount(0)
  })
})
