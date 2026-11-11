import type { Page } from '@playwright/test'

import { expect, test } from '../support'

const ADDRESS = '8.8.4.4'
const ATTACKER = '93.184.216.34'

/** Rules on what is typed on the Threat intelligence page, in the window that opens. */
async function ruleFromThePage(page: Page, subject: string, verdict: 'safe' | 'suspicious') {
  await page.getByTestId('rulings-subject').locator('input').fill(subject)
  await page.getByTestId('rulings-rule').click()
  const dialog = page.getByTestId('ruling-dialog')
  await expect(dialog.getByTestId('ruling-subject')).toHaveText(subject)
  await dialog.getByTestId(`ruling-choice-${verdict}`).click()
  return dialog
}

test.describe('ruling on a threat', () => {
  test('rules an address safe with a reason, with no service connected, and it is still there after a reload', async ({
    page,
  }) => {
    await page.goto('/threat-intelligence')
    const card = page.getByTestId('threat-rulings')
    await expect(card.getByTestId('rulings-empty')).toBeVisible()

    const dialog = await ruleFromThePage(page, ADDRESS, 'safe')
    await dialog.getByTestId('ruling-note').locator('textarea').fill("A friend's server")
    await dialog.getByTestId('ruling-save').click()
    await expect(dialog.getByTestId('ruling-lead')).toContainText('You ruled it safe')
    await dialog.getByTestId('ruling-done').click()

    const row = card.getByTestId('ruling-row')
    await expect(row).toHaveCount(1)
    await expect(row.getByTestId('ruling-subject-name')).toHaveText(ADDRESS)
    await expect(row.getByTestId('ruling-verdict')).toHaveText('Safe')
    await expect(row.getByTestId('ruling-note-text')).toContainText("A friend's server")

    await page.reload()

    await expect(page.getByTestId('threat-rulings').getByTestId('ruling-verdict')).toHaveText(
      'Safe',
    )
  })

  test('changes a ruling to suspicious and takes it back', async ({ page }) => {
    await page.goto('/threat-intelligence')
    const card = page.getByTestId('threat-rulings')
    const dialog = await ruleFromThePage(page, ADDRESS, 'safe')
    await dialog.getByTestId('ruling-save').click()
    await expect(dialog.getByTestId('ruling-lead')).toContainText('You ruled it safe')
    await dialog.getByTestId('ruling-done').click()

    await card.getByTestId('ruling-change').click()
    const again = page.getByTestId('ruling-dialog')
    await expect(again.getByTestId('ruling-choice-safe').locator('input')).toBeChecked()
    await again.getByTestId('ruling-choice-suspicious').click()
    await again.getByTestId('ruling-save').click()
    await expect(again.getByTestId('ruling-lead')).toContainText('You ruled it suspicious')
    await again.getByTestId('ruling-done').click()
    await expect(card.getByTestId('ruling-verdict')).toHaveText('Suspicious')

    await card.getByTestId('ruling-remove').click()

    await expect(card.getByTestId('rulings-empty')).toBeVisible()
  })

  test('refuses what is on the home network and says why', async ({ page }) => {
    await page.goto('/threat-intelligence')

    const dialog = await ruleFromThePage(page, '192.168.1.20', 'safe')
    await dialog.getByTestId('ruling-save').click()

    await expect(dialog.getByTestId('ruling-problem')).toContainText(
      "isn't a public internet address",
    )
    await dialog.getByTestId('ruling-done').click()
    await expect(page.getByTestId('rulings-empty')).toBeVisible()
  })

  test('rules on an address from the incident that names it, and the incident shows it', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([
      {
        address: ATTACKER,
        severity: 'high',
        programs: ['wazuh', 'ntopng'],
        signals: 4,
        twin: 'opnsense',
        detailed: true,
        minutes_ago: 5,
      },
    ])
    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
    const talk = page.getByTestId('conversation').first()
    // The device on the network is not offered: only what is on the internet can be ruled on.
    await expect(talk.getByTestId('end-server').getByTestId('end-rule')).toHaveCount(0)

    await talk.getByTestId('end-client').getByTestId('end-rule').click()
    const dialog = page.getByTestId('ruling-dialog')
    await expect(dialog.getByTestId('ruling-subject')).toHaveText(ATTACKER)
    await dialog.getByTestId('ruling-choice-safe').click()
    await dialog.getByTestId('ruling-note').locator('textarea').fill('My own scanner')
    await dialog.getByTestId('ruling-save').click()
    await expect(dialog.getByTestId('ruling-lead')).toContainText('You ruled it safe')
    await dialog.getByTestId('ruling-done').click()

    const end = talk.getByTestId('end-client')
    await expect(end.getByTestId('end-ruling')).toHaveText('You ruled it safe')
    await expect(end.getByTestId('end-ruling-note')).toContainText('My own scanner')
    await expect(end.getByTestId('end-rule')).toHaveText('Change my ruling')
    await expect(end).not.toHaveClass(/end--flagged/)

    await page.goto('/threat-intelligence')

    await expect(page.getByTestId('ruling-subject-name')).toHaveText(ATTACKER)
  })
})
