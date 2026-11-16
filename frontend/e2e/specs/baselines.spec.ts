import { expect, test } from '../support'

const LAPTOP = '192.168.1.20'
const TV = '192.168.1.30'

test.describe('baselines', () => {
  test('is in the menu, and has a title of its own', async ({ page, shell, baselines }) => {
    await page.goto('/')

    await shell.goTo('baselines')

    await expect(page).toHaveURL('/baselines')
    await expect(page).toHaveTitle('Baselines · AresGate')
    await shell.expectCurrent('baselines')
    await expect(baselines.heading).toHaveText('Baselines')
  })

  test('says that nothing is collected or learned, and what to do about it', async ({
    baselines,
  }) => {
    await baselines.goto()

    await expect(baselines.uncounted).toContainText('Connect your firewall')
    await expect(baselines.talkersEmpty).toContainText('Nothing is learned yet')
  })

  test.describe('with what is learned', () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createBaselines({
        interfaces: [
          { interface: 'igc0', megabytes: 100, unusual_hours_ago: 5 },
          { interface: 'igc0', direction: 'sent', megabytes: 20 },
        ],
        places: [
          { client: LAPTOP, network: '198.51.100.0/24', hits: 40 },
          { client: LAPTOP, network: '203.0.113.0/24', port: 22, hits: 3, expected: true },
          { client: TV, network: '192.0.2.0/24', hits: 8, days: 2 },
        ],
      })
    })

    test('draws what is usual for each direction, and the hours that were far above it', async ({
      baselines,
    }) => {
      await baselines.goto()

      await expect(baselines.charts).toHaveCount(2)
      await expect(baselines.charts.first()).toContainText('igc0: received')
      await expect(baselines.charts.first()).toContainText('Busiest at 00:00 with 100.0 MB')
      await expect(baselines.deviations).toContainText('500.0 MB against 100.0 MB usual.')
    })

    test('lists the devices, and says which are judged and which are still learning', async ({
      baselines,
    }) => {
      await baselines.goto()

      await expect(baselines.talkers).toHaveCount(2)
      await expect(baselines.talkers.first()).toContainText(LAPTOP)
      await expect(baselines.talkers.first()).toContainText('Places: 2 (1 expected)')
      await expect(baselines.talkers.first()).toContainText('Learning')
    })

    test('opens the places of a device, which are in the address of the page', async ({
      page,
      baselines,
    }) => {
      await baselines.goto()

      await baselines.talkers.first().click()

      await expect(page).toHaveURL(`/baselines?device=${LAPTOP}`)
      await expect(baselines.placeRows).toHaveCount(2)
      await expect(baselines.placeRows.first()).toContainText('203.0.113.0/24, port 22')
      await expect(baselines.placeRows.first()).toContainText('Expected')
      await page.reload()
      await expect(baselines.places).toBeVisible()
    })

    test('expects a place, and takes that off again', async ({ baselines }) => {
      await baselines.goto(`?device=${LAPTOP}`)
      const place = baselines.place('198.51.100.0/24')

      await place.getByRole('button', { name: /^Expect/ }).click()
      await expect(place).toContainText('Expected')
      await place.getByRole('button', { name: /^No longer expect/ }).click()

      await expect(place).not.toContainText('Expected')
    })

    test('expects a place never learned, and says why one cannot be kept', async ({
      baselines,
    }) => {
      await baselines.goto(`?device=${LAPTOP}`)

      await baselines.networkField.fill('192.0.2.0/16')
      await baselines.addPlace.click()
      await expect(baselines.failure).toContainText('Places are kept as a /24.')
      await baselines.networkField.fill('192.0.2.0/24')
      await baselines.portField.fill('53')
      await baselines.addPlace.click()

      await expect(baselines.place('192.0.2.0/24')).toContainText('Expected')
      await expect(baselines.placeRows).toHaveCount(3)
    })

    test('forgets a place, after asking', async ({ page, baselines }) => {
      await baselines.goto(`?device=${LAPTOP}`)

      await baselines
        .place('198.51.100.0/24')
        .getByRole('button', { name: /^Forget/ })
        .click()
      await page.getByTestId('confirm-dialog').getByRole('button', { name: 'Forget' }).click()

      await expect(baselines.placeRows).toHaveCount(1)
      await expect(baselines.talkers.first()).toContainText('Places: 1')
    })
  })
})
