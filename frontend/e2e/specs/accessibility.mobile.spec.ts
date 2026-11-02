import { expect, expectAccessible, test } from '../support'

// Only a phone has the bottom bar and the sheet of places behind More.
for (const theme of ['light', 'dark'] as const) {
  test.describe(`accessibility of the bottom bar in the ${theme} theme`, () => {
    test('the bar, and the sheet behind More, have no WCAG 2.2 AA problems', async ({
      page,
      dashboard,
      shell,
    }) => {
      await dashboard.goto()
      await expect(dashboard.banner).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await shell.moreButton.click()
      await expect(shell.moreSheet).toBeVisible()
      await expectAccessible(page)
    })

    test('the cards of assets have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      assets,
      shell,
    }) => {
      await harness.createAssets({
        devices: [
          {
            hostname: 'laptop',
            mac: '00:11:22:0a:0b:0c',
            vendor: 'Example Devices Inc.',
            addresses: ['192.168.1.20', '192.168.1.21', '192.168.1.22', '192.168.1.23'],
            listed: [
              { source: 'opnsense', via: 'arp', minutes_ago: 1 },
              { source: 'opnsense', via: 'dhcp', minutes_ago: 1 },
              { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
            ],
          },
          { mac: '02:aa:bb:cc:dd:ee', listed: [{ via: 'dhcp', minutes_ago: 30 }] },
        ],
        hosts: [{ key: '002', hostname: 'laptop', address: '192.168.1.20' }],
      })
      await assets.goto()
      await expect(assets.cards).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the cards of logs have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      logs,
      shell,
    }) => {
      await harness.createEvents([
        { summary: 'Blocked tcp', src_address: '203.0.113.7', dst_address: '192.168.1.20' },
        { kind: 'alert', severity: 'high', summary: 'ET SCAN', seconds_ago: 90 },
      ])
      await logs.goto()
      await expect(logs.cards).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)
    })
  })
}
