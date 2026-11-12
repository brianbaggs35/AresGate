import { expect, test } from '../support'

const ADDRESS = '93.184.216.34'

test.describe('what was said on the wire, on a phone', () => {
  test('fits the screen, with no sideways scroll', async ({ harness, page }) => {
    await harness.createIncidents([
      {
        address: ADDRESS,
        severity: 'medium',
        programs: ['opnsense'],
        signals: 3,
        detailed: true,
        wire: true,
        outbound: true,
        minutes_ago: 5,
      },
    ])
    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ADDRESS }).click()

    const card = page.getByTestId('wire-card')
    await expect(card).toBeVisible()
    await card.getByTestId('wire-panel-requests').getByRole('button').click()
    await expect(card.getByTestId('wire-request')).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
