import { expect, test } from '../support'

test.describe('ruling on a threat, on a phone', () => {
  test('the window fills the screen and nothing scrolls sideways', async ({ page }) => {
    await page.goto('/threat-intelligence')
    await page.getByTestId('rulings-subject').locator('input').fill('8.8.4.4')
    await page.getByTestId('rulings-rule').click()
    const dialog = page.getByTestId('ruling-dialog')

    await expect(dialog.getByTestId('ruling-choice-safe')).toBeVisible()
    await expect(dialog.getByTestId('ruling-choice-suspicious')).toBeVisible()
    const box = await dialog.boundingBox()
    const viewport = page.viewportSize()
    expect(box?.width).toBeGreaterThanOrEqual((viewport?.width ?? 0) * 0.9)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
