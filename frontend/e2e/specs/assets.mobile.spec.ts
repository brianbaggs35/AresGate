import { expect, test } from '../support'

/** A device that is listed by three programs, at four addresses, with a long name: the most a
 * card has to fit across a phone. */
const BUSY = {
  hostname: 'a-device-with-a-rather-long-name-that-has-to-wrap-on-a-phone',
  mac: '00:11:22:0a:0b:0c',
  vendor: 'Example Devices International Incorporated',
  addresses: ['192.168.1.20', '192.168.1.21', '192.168.1.22', 'fd00:1234:5678:9abc::20'],
  listed: [
    { source: 'opnsense', via: 'arp' as const, minutes_ago: 1 },
    { source: 'opnsense', via: 'dhcp' as const, minutes_ago: 1 },
    { source: 'ntopng', via: 'hosts' as const, minutes_ago: 1 },
  ],
}

test.describe('assets on a phone', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createAssets({
      devices: [BUSY, { hostname: 'phone', mac: '02:aa:bb:cc:dd:ee', listed: [{ via: 'dhcp' }] }],
      hosts: [{ key: '002', hostname: 'build-server', address: '192.168.1.50' }],
    })
  })

  test('is reached through More, which the bar keeps for the places that do not fit', async ({
    page,
    shell,
  }) => {
    await page.goto('/')

    await shell.goTo('assets')

    await expect(page).toHaveURL('/assets')
    await shell.expectCurrent('assets')
  })

  test('fits the screen, with a card as wide as it, however much is on it', async ({
    assets,
    page,
  }) => {
    await assets.goto()
    await expect(assets.cards).toHaveCount(3)

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    const viewport = page.viewportSize()
    for (const card of await assets.cards.all()) {
      const box = await card.boundingBox()
      expect(box?.width ?? 0).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(viewport?.width ?? 0)
    }
  })

  test('stacks what a card says, one thing under another', async ({ assets }) => {
    await assets.goto()
    const card = assets.cards.first()
    const [status, addresses, sources] = await Promise.all([
      card.getByTestId('asset-status').boundingBox(),
      card.getByTestId('asset-addresses').boundingBox(),
      card.getByTestId('asset-sources').boundingBox(),
    ])

    expect((addresses?.y ?? 0) + 1).toBeGreaterThan((status?.y ?? 0) + (status?.height ?? 0))
    expect((sources?.y ?? 0) + 1).toBeGreaterThan((addresses?.y ?? 0) + (addresses?.height ?? 0))
  })

  test('has choices a thumb can hit', async ({ assets }) => {
    await assets.goto()
    await expect(assets.cards).toHaveCount(3)

    for (const choice of [
      assets.view('all'),
      assets.view('online'),
      assets.newOnly,
      assets.unidentified,
      assets.refresh,
      assets.search,
    ]) {
      const box = await choice.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(36)
    }
  })

  test('keeps the states in one row that scrolls, rather than a block that pushes the list down', async ({
    assets,
  }) => {
    await assets.goto()
    const views = await assets.views.boundingBox()
    const first = await assets.cards.first().boundingBox()

    // One row of buttons, not a stack of them.
    expect(views?.height ?? Infinity).toBeLessThan(80)
    expect(first?.y ?? 0).toBeGreaterThan((views?.y ?? 0) + (views?.height ?? 0))
  })

  test('narrows with a tap, and keeps the choice in the address', async ({ assets, page }) => {
    await assets.goto()

    await assets.view('online').tap()

    await expect(page).toHaveURL('/assets?status=online')
    await expect(assets.cards).toHaveCount(2)
  })

  test('puts a place to type under the heading, with the keyboard hint for search', async ({
    assets,
  }) => {
    await assets.goto()

    await expect(assets.search).toHaveAttribute('enterkeyhint', 'search')
    await expect(assets.search).toHaveAttribute('type', 'search')
  })
})
