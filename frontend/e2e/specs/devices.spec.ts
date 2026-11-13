import { expect, test } from '../support'

const LAPTOP_IP = '192.168.1.20'
const CAMERA_IP = '192.168.1.30'
const SERVER = '93.184.216.34'
const SCANNER = '8.8.8.8'

test.describe('devices', () => {
  test('is in the menu, and has a title of its own', async ({ page, shell, devices }) => {
    await page.goto('/')

    await shell.goTo('devices')

    await expect(page).toHaveURL('/devices')
    await expect(page).toHaveTitle('Devices · AresGate')
    await shell.expectCurrent('devices')
    await expect(devices.heading).toHaveText('Devices')
  })

  test('says that nothing has been reported yet, and leads to the integrations', async ({
    devices,
    page,
  }) => {
    await devices.goto()

    await expect(devices.emptyTitle).toHaveText('No connections yet')

    await devices.empty.getByTestId('empty-integrations').click()

    await expect(page).toHaveURL('/integrations')
  })

  test.describe('with connections reported', () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createAssets({
        devices: [
          {
            hostname: 'laptop',
            mac: '00:11:22:0a:0b:0c',
            vendor: 'Example Devices Inc.',
            addresses: [LAPTOP_IP],
            listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
          },
          {
            hostname: 'camera',
            mac: '00:11:22:0a:0b:0d',
            addresses: [CAMERA_IP],
            listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
          },
        ],
      })
      await harness.createEvents([
        {
          src_address: LAPTOP_IP,
          src_port: 51000,
          dst_address: SERVER,
          dst_port: 443,
          protocol: 'tcp',
          repeat: 3,
          seconds_ago: 120,
        },
        {
          src_address: SCANNER,
          src_port: 40000,
          dst_address: CAMERA_IP,
          dst_port: 23,
          protocol: 'tcp',
          repeat: 2,
          seconds_ago: 60,
        },
      ])
    })

    test('lists every address in a connection, with how many each way', async ({ devices }) => {
      await devices.goto()

      await expect(devices.cards).toHaveCount(4)
      await expect(devices.count('all')).toHaveText('4')
      await expect(devices.count('yours')).toHaveText('2')
      await expect(devices.count('outside')).toHaveText('2')
      const laptop = devices.card(LAPTOP_IP)
      await expect(laptop.getByTestId('device-outgoing')).toContainText('3 out')
      await expect(laptop.getByTestId('device-asset')).toHaveText('laptop')
      const server = devices.card(SERVER)
      await expect(server.getByTestId('device-incoming')).toContainText('3 in')
      await expect(server.getByTestId('device-ports')).toContainText('443/tcp')
      await expect(devices.note).toContainText('not every packet')
    })

    test('narrows to the ones on the Internet, and keeps that in the address', async ({
      devices,
      page,
    }) => {
      await devices.goto()

      await devices.view('outside').click()

      await expect(page).toHaveURL(/scope=outside/)
      await expect(devices.cards).toHaveCount(2)
      await expect(devices.addresses).toContainText([SCANNER, SERVER])
    })

    test('finds a device by the name of the asset it is', async ({ devices }) => {
      await devices.goto()

      await devices.find('camera')

      await expect(devices.cards).toHaveCount(1)
      await expect(devices.addresses).toHaveText([CAMERA_IP])
      await expect(devices.clear).toBeVisible()

      await devices.clear.click()

      await expect(devices.cards).toHaveCount(4)
    })

    test('opens the page of a device, with what it connected to and over which port', async ({
      devices,
      device,
      page,
    }) => {
      await devices.goto()

      await devices.open(LAPTOP_IP)

      await expect(page).toHaveURL(`/devices/${LAPTOP_IP}`)
      await expect(device.heading).toHaveText(LAPTOP_IP)
      await expect(device.description).toContainText('laptop')
      await expect(device.outgoingTile).toContainText('3')
      await expect(device.connectionRows).toHaveCount(1)
      await expect(device.connectionRows.first()).toContainText(SERVER)
      await expect(device.connectionRows.first()).toContainText('443/tcp')
      await expect(device.events).toHaveCount(3)
      await expect(device.noIncidents).toBeVisible()
      await expect(device.assetLink).toHaveAttribute('href', /\/assets\/device-\d+/)
    })

    test('goes from a connection to the device at the other end, and back to the list', async ({
      devices,
      device,
      page,
    }) => {
      await page.goto(`/devices/${LAPTOP_IP}`)

      await device.connectionRows.first().getByTestId('connection-peer').click()

      await expect(page).toHaveURL(`/devices/${SERVER}`)
      await expect(device.incomingTile).toContainText('3')

      await device.back.click()

      await expect(page).toHaveURL('/devices')
      await expect(devices.cards).toHaveCount(4)
    })

    test('says that nothing is known of an address that was in no connection', async ({
      device,
      page,
    }) => {
      await page.goto('/devices/203.0.113.77')

      await expect(device.missing).toContainText('Nothing is known of that address')
    })
  })

  test.describe('with an attack', () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createIncidents([{ address: SCANNER, severity: 'critical' }])
    })

    test('marks the devices in an incident, and leads to it from their page', async ({
      devices,
      device,
      page,
    }) => {
      await devices.goto()

      await devices.flagged.click()

      await expect(page).toHaveURL(/flagged=1/)
      await expect(devices.card(SCANNER).getByTestId('device-incidents')).toContainText(
        'In 1 incident',
      )

      await devices.open(SCANNER)

      await expect(device.incidents).toHaveCount(1)
      await device.incidents.first().getByTestId('device-incident-link').click()

      await expect(page).toHaveURL(/\/incidents\/\d+/)
    })
  })
})
