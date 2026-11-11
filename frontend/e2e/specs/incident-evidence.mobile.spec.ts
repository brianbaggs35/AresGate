import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

test.describe('what the programs said of an incident, on a phone', () => {
  test('fits the screen, with no sideways scroll', async ({ harness, page }) => {
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

    await expect(page.getByTestId('insights-card')).toBeVisible()
    await expect(page.getByTestId('conversations-card')).toBeVisible()
    await expect(page.getByTestId('coverage-card')).toBeVisible()
    await expect(page.getByTestId('evidence-excerpt').first()).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
