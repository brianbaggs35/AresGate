import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

const ADDRESS = '93.184.216.34'

/** A camera's call to its cloud, which a signature says is a threat. */
const CAMERA_CALL: IncidentRequest = {
  address: ADDRESS,
  severity: 'critical',
  programs: ['opnsense', 'wazuh'],
  signals: 3,
  device: '192.168.1.30',
  device_name: 'Blink camera',
}

async function expectFitsTheScreen(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
}

/** Trusts the address from the page of its incident, everything about it, with a reason. */
async function trustFromTheIncident(page: Page, note: string): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ADDRESS }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
  await page.getByTestId('trust-button').first().click()
  await page.getByTestId('scope-address').click()
  await page.getByTestId('field-note').locator('input').fill(note)
  await page.getByTestId('trust-save').click()
  await expect(page.getByTestId('notice')).toContainText(`Everything about ${ADDRESS}`)
}

test.describe('trust', () => {
  test('is in the menu, says what it is for, and has nothing on a new install', async ({
    page,
    shell,
  }) => {
    await page.goto('/')

    await shell.goTo('trust')

    await expect(page).toHaveURL('/trust')
    await expect(page).toHaveTitle('Trust · AresGate')
    await shell.expectCurrent('trust')
    await expect(page.getByTestId('trust-info')).toContainText('every signal that matches it')
    await expect(page.getByTestId('no-trust')).toContainText("You haven't trusted anything yet")
    await expect(page.getByTestId('add-trust')).toBeVisible()
    await expectFitsTheScreen(page)
    await expectAccessible(page)
  })

  test('trusts an address from its incident, and lists it, with what it kept quiet', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([CAMERA_CALL])

    await trustFromTheIncident(page, 'Blink camera')

    await page.goto('/trust')
    const row = page.getByTestId('trust-row')
    await expect(row).toHaveCount(1)
    await expect(row.getByTestId('trust-about')).toHaveText(`Everything about ${ADDRESS}`)
    await expect(row.getByTestId('trust-level')).toHaveText('Safe')
    await expect(row.getByTestId('trust-note')).toHaveText('“Blink camera”')
    await expect(row.getByTestId('trust-applied')).toContainText('Kept')
    await expect(page.getByTestId('trust-tiles')).toContainText('Safe')
    await expectFitsTheScreen(page)
    await expectAccessible(page)
  })

  test('trusts something that is not on the screen, by its own form', async ({ page }) => {
    await page.goto('/trust')

    await page.getByTestId('add-trust').click()
    await page.getByTestId('trust-save').click()
    await expect(page.getByTestId('trust-problem')).toContainText('Say what to trust')
    await page.getByTestId('field-address').locator('input').fill('52.1.2.3')
    await page.getByTestId('level-low_priority').locator('input').check()
    await page.getByTestId('trust-save').click()

    await expect(page.getByTestId('trust-notice')).toContainText(
      'Trusted: Everything about 52.1.2.3',
    )
    await expect(page.getByTestId('trust-level')).toHaveText('Low priority')
  })

  test('changes everything about a decision on its own page', async ({ harness, page }) => {
    await harness.createIncidents([CAMERA_CALL])
    await trustFromTheIncident(page, 'first reason')
    await page.goto('/trust')

    await page.getByTestId('trust-open').click()

    await expect(page).toHaveURL(/\/trust\/\d+$/)
    await expect(page.getByTestId('decision-info')).toContainText('never raises an alarm')
    await expect(page.getByTestId('field-address').locator('input')).toHaveValue(ADDRESS)
    await expectFitsTheScreen(page)
    await expectAccessible(page)

    await page.getByTestId('field-note').locator('input').fill('second reason')
    await page.getByTestId('level-low_priority').locator('input').check()
    await page.getByTestId('trust-save').click()

    await expect(page.getByTestId('decision-notice')).toContainText('Saved')
    await expect(page.getByTestId('decision-level')).toHaveText('Low priority')
    await page.getByRole('link', { name: 'Trust', exact: true }).first().click()
    await expect(page.getByTestId('trust-note')).toHaveText('“second reason”')
  })

  test('takes a decision back from the list, after asking', async ({ harness, page }) => {
    await harness.createIncidents([CAMERA_CALL])
    await trustFromTheIncident(page, 'camera')
    await page.goto('/trust')

    await page.getByTestId('trust-revoke').click()
    await expect(page.getByTestId('confirm-message')).toContainText(`Everything about ${ADDRESS}`)
    await page.getByTestId('confirm-cancel').click()
    await expect(page.getByTestId('trust-row')).toHaveCount(1)

    await page.getByTestId('trust-revoke').click()
    await page.getByTestId('confirm-accept').click()

    await expect(page.getByTestId('trust-notice')).toContainText('Taken back')
    await expect(page.getByTestId('no-trust')).toBeVisible()
  })

  test('takes a decision back from its own page, and goes back to the list', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([CAMERA_CALL])
    await trustFromTheIncident(page, 'camera')
    await page.goto('/trust')
    await page.getByTestId('trust-open').click()

    await page.getByTestId('decision-revoke').click()
    await page.getByTestId('confirm-accept').click()

    await expect(page).toHaveURL('/trust')
    await expect(page.getByTestId('no-trust')).toBeVisible()
  })

  test('says a decision that is gone is, and does not offer to try again', async ({ page }) => {
    await page.goto('/trust/999999')

    await expect(page.getByTestId('decision-error')).toContainText('It may have been taken back.')
    await expectAccessible(page)
  })
})
