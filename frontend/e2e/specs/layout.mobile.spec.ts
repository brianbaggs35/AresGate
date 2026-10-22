import { expect, test } from '../support'

test.describe('layout on a phone', () => {
  test('the overview fits the screen without scrolling sideways', async ({ page, overview }) => {
    await overview.goto()
    await expect(overview.databaseStatus).toHaveText('Database: Connected')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('the status card uses nearly the whole width', async ({ page, overview }) => {
    await overview.goto()

    const box = await overview.card.boundingBox()
    const viewport = page.viewportSize()

    expect(box?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
  })
})
