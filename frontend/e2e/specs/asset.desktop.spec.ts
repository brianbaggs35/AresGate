import { expect, test } from '../support'

test.describe('an asset on a computer', () => {
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

  test('shows the four figures in one row, with the traffic and its choices below them', async ({
    assets,
    asset,
  }) => {
    await assets.goto()
    await assets.open('laptop')
    await expect(asset.heading).toHaveText('laptop')

    const tiles = await Promise.all(
      [asset.listedTile, asset.sentTile, asset.receivedTile, asset.eventsTile].map((tile) =>
        tile.boundingBox(),
      ),
    )
    const top = tiles[0]?.y ?? 0
    for (const tile of tiles) {
      expect(Math.abs((tile?.y ?? 0) - top)).toBeLessThan(2)
    }
    const windows = await asset.windows.boundingBox()
    expect(windows?.y ?? 0).toBeGreaterThan(top + (tiles[0]?.height ?? 0))
  })
})
