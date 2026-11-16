import { expect, test } from '../support'

// A phone keeps the cards, so the table is for the desktop project only.
test.describe('reading the incidents as a table', () => {
  test('is a table when asked, sorted by a column, grouped by address, and stays so after a reload', async ({
    page,
    harness,
    incidents,
  }) => {
    // The same address twice, with more than the gap between signals (six hours) between them: a
    // nearer one would be a second look at the first incident, not another.
    await harness.createIncidents([
      { address: '20.20.1.20', minutes_ago: 600, signals: 2 },
      { address: '20.20.2.20', minutes_ago: 2, signals: 5 },
      { address: '20.20.1.20', minutes_ago: 1, signals: 3 },
    ])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    await expect(page.getByTestId('incident-table')).toHaveCount(0)

    await page.getByTestId('layout-table').click()

    await expect(page.getByTestId('incident-table')).toBeVisible()
    await expect(incidents.cards).toHaveCount(3)
    const sort = page.getByTestId('sort-signals')
    await sort.click()
    await expect(page.getByTestId('column-signals')).toHaveAttribute('aria-sort', 'descending')
    await expect(page.getByTestId('row-signals').first()).toHaveText('5')

    await page.getByTestId('group-by-address').click()
    await expect(page.getByTestId('incident-group')).toHaveCount(1)
    await expect(page.getByTestId('group-count')).toContainText('2 incidents')
    await page.getByTestId('group-fold').click()
    await expect(incidents.cards).toHaveCount(1)
    await page.getByTestId('group-fold').click()
    await expect(incidents.cards).toHaveCount(3)

    await page.getByTestId('group-select').check()
    await expect(page.getByTestId('bulk-count')).toHaveText('2 selected')

    await page.reload()
    await expect(page.getByTestId('incident-table')).toBeVisible()
    await expect(page.getByTestId('incident-group')).toHaveCount(1)
  })
})
