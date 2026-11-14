import type { AssetDeviceRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

const TOKEN = 'a-valid-ntopng-token'

/** A laptop that two programs list. */
const LAPTOP: AssetDeviceRequest = {
  hostname: 'laptop',
  mac: '00:11:22:0a:0b:0c',
  vendor: 'Example Devices Inc.',
  addresses: ['192.168.1.20'],
  listed: [
    { source: 'opnsense', via: 'arp', minutes_ago: 1 },
    { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
  ],
}

test.describe('looking at the packets of an asset', () => {
  test.beforeEach(async ({ harness, page }) => {
    await harness.createAssets({ devices: [LAPTOP] })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'laptop' }).click()
    await expect(page).toHaveURL(/\/assets\/device-\d+$/)
  })

  test('says to connect ntopng first when it is not connected', async ({ asset }) => {
    await expect(asset.capture).toBeVisible()

    await asset.captureStart.click()

    await expect(asset.captureFailure).toHaveText('Connect ntopng first.')
    await expect(asset.capturePackets).toHaveCount(0)
  })

  test('shows what ntopng saw of the device, packet by packet', async ({
    asset,
    harness,
    integration,
    page,
  }) => {
    const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
    await integration.goto('ntopng')
    await integration.address('api').fill(ntopng.url)
    await integration.field('api', 'token').fill(TOKEN)
    await integration.save.click()
    await expect(integration.status).toHaveText('Connected')
    await page.goBack()
    await page.reload()

    await asset.captureStart.click()

    await expect(asset.captureSummary).toContainText(
      '6 packets to or from 192.168.1.20 in 10 seconds',
    )
    await expect(asset.capturePackets).toHaveCount(6)
    await expect(asset.capturePackets.first()).toContainText('192.168.1.20:50000')
    await expect(asset.capturePackets.first()).toContainText('TCP SYN')
    await expect(asset.capturePackets.nth(3)).toContainText('GET / HTTP/1.1')
    await expect(asset.capture.getByTestId('capture-protocol')).toHaveText(['TCP 5', 'UDP 1'])
    await expectAccessible(page)
  })
})
