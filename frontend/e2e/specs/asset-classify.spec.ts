import type { AssetDeviceRequest, IncidentRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

const ATTACKER = '93.184.216.34'

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

/** An attack on a device that its name says is a camera. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['opnsense', 'wazuh'],
  signals: 4,
  minutes_ago: 5,
  device: '192.168.1.20',
  device_name: 'Kitchen camera',
}

test.describe('saying what an asset is', () => {
  test('is done on the page of the asset, and shows on the list', async ({ harness, page }) => {
    await harness.createAssets({ devices: [LAPTOP] })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'laptop' }).click()
    await expect(page).toHaveURL(/\/assets\/device-\d+$/)

    const card = page.getByTestId('asset-classify')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('asset-classify-save')).toBeDisabled()
    await card
      .getByTestId('asset-kind-choice')
      .filter({ hasText: /^Laptop$/ })
      .click()
    await card.getByTestId('asset-purpose').locator('input').fill('Used for work')
    await card.getByTestId('asset-classify-save').click()

    await expect(card.getByTestId('asset-classify-saved')).toBeVisible()
    await expect(page.getByTestId('asset-kind')).toHaveText('Laptop')
    await expect(page.getByTestId('asset-purpose-line')).toHaveText('Used for work')

    await page.goto('/assets')
    const listed = page.getByTestId('asset-card').filter({ hasText: 'laptop' })
    await expect(listed.getByTestId('asset-kind')).toHaveText('Laptop')
    await expect(listed.getByTestId('asset-purpose')).toHaveText('Used for work')
  })

  test('can be taken back', async ({ harness, page }) => {
    await harness.createAssets({ devices: [LAPTOP] })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'laptop' }).click()
    const card = page.getByTestId('asset-classify')
    await card
      .getByTestId('asset-kind-choice')
      .filter({ hasText: /^Laptop$/ })
      .click()
    await card.getByTestId('asset-classify-save').click()
    await expect(page.getByTestId('asset-kind')).toBeVisible()

    await card.getByTestId('asset-classify-clear').click()

    await expect(page.getByTestId('asset-kind')).toHaveCount(0)
    await expect(card.getByTestId('asset-classify-clear')).toHaveCount(0)
  })

  test('suggests a kind from the name, and uses it only when asked', async ({ harness, page }) => {
    await harness.createAssets({
      devices: [{ ...LAPTOP, hostname: 'garage-camera', addresses: ['192.168.1.30'] }],
    })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'garage-camera' }).click()

    const card = page.getByTestId('asset-classify')
    await expect(card.getByTestId('asset-suggestion')).toContainText('camera')
    await card.getByTestId('asset-suggestion-use').click()
    await expect(card.getByTestId('asset-suggestion')).toHaveCount(0)
    await card.getByTestId('asset-classify-save').click()

    await expect(page.getByTestId('asset-kind')).toContainText('Camera')
  })

  test('narrows the list to a kind, and to what has none', async ({ harness, page }) => {
    await harness.createAssets({
      devices: [
        LAPTOP,
        { ...LAPTOP, hostname: 'phone', mac: '02:aa:bb:cc:dd:ee', addresses: ['192.168.1.9'] },
      ],
    })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'laptop' }).click()
    const card = page.getByTestId('asset-classify')
    await card
      .getByTestId('asset-kind-choice')
      .filter({ hasText: /^Laptop$/ })
      .click()
    await card.getByTestId('asset-classify-save').click()
    await expect(page.getByTestId('asset-kind')).toBeVisible()

    await page.goto('/assets?kind=laptop')
    await expect(page.getByTestId('asset-card')).toHaveCount(1)
    await expect(page.getByTestId('asset-name')).toHaveText('laptop')

    await page.goto('/assets?kind=unclassified')
    await expect(page.getByTestId('asset-card')).toHaveCount(1)
    await expect(page.getByTestId('asset-name')).toHaveText('phone')
  })

  test('fits the screen and has no accessibility violations', async ({ harness, page }) => {
    await harness.createAssets({ devices: [LAPTOP] })
    await page.goto('/assets')
    await page.getByTestId('asset-link').filter({ hasText: 'laptop' }).click()

    await expect(page.getByTestId('asset-classify')).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    await expectAccessible(page)
  })
})

test.describe('the devices an incident went through', () => {
  test('lists the device it was about as the Assets page lists it, and asks what it is', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([ATTACK])
    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()

    const card = page.getByTestId('through-card')
    await expect(card).toBeVisible()
    const target = card.getByTestId('through-stop').filter({ hasText: 'The device it was about' })
    await expect(target.getByTestId('asset-name')).toHaveText('Kitchen camera')

    await target.getByTestId('through-classify').click()

    await expect(page).toHaveURL(/\/assets\/device-\d+$/)
    await expect(page.getByTestId('asset-suggestion')).toContainText('camera')
  })

  test('shows what the owner said once they have said it', async ({ harness, page }) => {
    await harness.createIncidents([ATTACK])
    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
    await expect(page).toHaveURL(/\/incidents\/\d+$/)
    const incident = page.url()
    await page.getByTestId('through-classify').click()
    const classify = page.getByTestId('asset-classify')
    await classify.getByTestId('asset-suggestion-use').click()
    await classify.getByTestId('asset-purpose').locator('input').fill('Watches the kitchen')
    await classify.getByTestId('asset-classify-save').click()
    await expect(page.getByTestId('asset-kind')).toBeVisible()

    await page.goto(incident)

    const target = page.getByTestId('through-stop').filter({ hasText: 'The device it was about' })
    await expect(target.getByTestId('asset-kind')).toContainText('Camera')
    await expect(target.getByTestId('asset-purpose')).toHaveText('Watches the kitchen')
    await expect(target.getByTestId('through-classify')).toHaveCount(0)
  })

  test('fits the screen and has no accessibility violations', async ({ harness, page }) => {
    await harness.createIncidents([ATTACK])
    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()

    await expect(page.getByTestId('through-card')).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    await expectAccessible(page)
  })
})
