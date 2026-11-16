import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

/** Each from a block of its own: addresses side by side are one bot. */
function many(count: number): IncidentRequest[] {
  return Array.from({ length: count }, (_, number) => ({
    address: `20.20.${(number + 1).toString()}.20`,
    minutes_ago: number + 1,
    signals: 2,
  }))
}

test.describe('reading the incidents for a long time', () => {
  test('is closer together when asked, and stays so after a reload', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(2))
    await incidents.goto()
    const html = page.locator('html')
    await expect(html).toHaveAttribute('data-density', 'comfortable')
    const roomy = (await incidents.cards.first().boundingBox())!.height

    await page.getByTestId('density-compact').click()

    await expect(html).toHaveAttribute('data-density', 'compact')
    await expect
      .poll(async () => (await incidents.cards.first().boundingBox())!.height)
      .toBeLessThan(roomy)
    await page.reload()
    await expect(html).toHaveAttribute('data-density', 'compact')
    await expect(page.getByTestId('density-compact')).toHaveAttribute('aria-pressed', 'true')
  })

  test('moves from one incident to the next with J and K, and opens one with Enter', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(3))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    const links = page.getByTestId('incident')

    await page.keyboard.press('j')
    await expect(links.nth(0)).toBeFocused()
    await page.keyboard.press('j')
    await expect(links.nth(1)).toBeFocused()
    await page.keyboard.press('k')
    await expect(links.nth(0)).toBeFocused()
    await page.keyboard.press('j')
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('picks the incident it is on with X', async ({ page, harness, incidents }) => {
    await harness.createIncidents(many(3))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)

    await page.keyboard.press('j')
    await page.keyboard.press('x')

    await expect(incidents.picked).toHaveText('1 selected')
  })

  test('says which keys there are when ? is pressed, and puts them away with Escape', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(1))
    await incidents.goto()

    await page.keyboard.press('?')

    const keys = page.getByTestId('shortcuts')
    await expect(keys).toBeVisible()
    await expect(keys).toContainText('Move to the next incident')
    await page.keyboard.press('Escape')
    await expect(keys).toBeHidden()
  })

  test('does not take a key typed into the search box for a shortcut', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(2))
    await incidents.goto()

    await incidents.searchField.fill('jjxx?')

    await expect(incidents.searchField).toHaveValue('jjxx?')
    await expect(page.getByTestId('shortcuts')).toBeHidden()
  })
})
