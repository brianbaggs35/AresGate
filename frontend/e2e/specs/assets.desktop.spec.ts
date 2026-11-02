import { expect, test } from '../support'

test.describe('assets on a computer', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createAssets({
      devices: [
        {
          hostname: 'laptop',
          mac: '00:11:22:0a:0b:0c',
          vendor: 'Example Devices Inc.',
          addresses: ['192.168.1.20'],
          listed: [
            { source: 'opnsense', via: 'arp', minutes_ago: 1 },
            { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
          ],
        },
      ],
    })
  })

  test('puts the state at the end of the first row of a card, and the facts side by side', async ({
    assets,
  }) => {
    await assets.goto()
    const card = assets.cards.first()
    await expect(card).toBeVisible()

    const [name, status, addresses, sources] = await Promise.all([
      card.getByTestId('asset-name').boundingBox(),
      card.getByTestId('asset-status').boundingBox(),
      card.getByTestId('asset-addresses').boundingBox(),
      card.getByTestId('asset-sources').boundingBox(),
    ])

    // The state is beside the name, to the right of it.
    expect(status?.x ?? 0).toBeGreaterThan((name?.x ?? 0) + (name?.width ?? 0))
    expect(Math.abs((status?.y ?? 0) - (name?.y ?? 0))).toBeLessThan(40)
    // The addresses and the programs that list it are in columns, side by side.
    expect(sources?.x ?? 0).toBeGreaterThan((addresses?.x ?? 0) + (addresses?.width ?? 0) - 1)
  })

  test('puts the states in a row, with how many each holds', async ({ assets }) => {
    await assets.goto()

    await expect(assets.views.getByRole('button')).toHaveText([
      'All 1',
      'Online 1',
      'Seen recently 0',
      'Not seen for a while 0',
    ])
  })
})
