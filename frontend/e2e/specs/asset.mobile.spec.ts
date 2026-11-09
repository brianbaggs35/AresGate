import { expect, test } from '../support'

test.describe('an asset on a phone', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createAssets({
      devices: [
        {
          hostname: 'laptop',
          mac: '00:11:22:0a:0b:0c',
          vendor: 'Example Devices Inc.',
          addresses: ['192.168.1.20'],
          listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
        },
      ],
    })
    await harness.createTraffic([
      { host: '192.168.1.20', sent: [1000, 3000, 6000, 10000], received: [500, 600, 700, 900] },
    ])
  })

  test('fits the screen, with no sideways scroll', async ({ assets, asset, page }) => {
    await assets.goto()
    await assets.open('laptop')
    await expect(asset.heading).toHaveText('laptop')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('stacks the four figures, one under another', async ({ assets, asset }) => {
    await assets.goto()
    await assets.open('laptop')
    await expect(asset.heading).toHaveText('laptop')

    const [first, second] = await Promise.all([
      asset.listedTile.boundingBox(),
      asset.sentTile.boundingBox(),
    ])
    expect((first?.y ?? 0) + (first?.height ?? 0)).toBeLessThanOrEqual(second?.y ?? 0)
  })

  test('has choices a thumb can hit', async ({ assets, asset }) => {
    await assets.goto()
    await assets.open('laptop')
    await expect(asset.heading).toHaveText('laptop')

    for (const choice of [asset.window('24 hours'), asset.window('7 days')]) {
      const box = await choice.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(36)
    }
  })
})
