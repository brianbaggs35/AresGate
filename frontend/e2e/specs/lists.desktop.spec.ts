import { expect, test } from '../support'

test.describe('views in the command palette', () => {
  test('are found by their page and name, and open the page with their filters', async ({
    page,
    harness,
    shell,
  }) => {
    await harness.createAssets({
      devices: [{ hostname: 'laptop', mac: '00:11:22:0a:0b:0c', listed: [{ via: 'dhcp' }] }],
      hosts: [],
    })
    await page.goto('/assets?q=laptop')
    await page.getByTestId('list-views-button').click()
    const panel = page.getByTestId('views-panel')
    await panel.getByTestId('view-name').getByRole('textbox').fill('Laptops')
    await panel.getByTestId('view-save').click()
    await expect(panel.getByTestId('views-notice')).toHaveText('Saved as Laptops.')
    await page.keyboard.press('Escape')
    await page.goto('/devices')

    await page.keyboard.press('Control+k')
    await shell.paletteSearch.fill('assets laptops')
    await expect(shell.paletteRows).toHaveText(['Assets: Laptops'])
    await shell.paletteRows.first().click()

    await expect(page).toHaveURL('/assets?q=laptop')
  })

  test('are on the page of the list they belong to, in two buttons', async ({ page, harness }) => {
    await harness.createIncidents([{ address: '20.20.1.20', minutes_ago: 5, signals: 2 }])
    await page.goto('/incidents')

    await expect(page.getByTestId('list-export')).toBeVisible()
    await expect(page.getByTestId('list-views-button')).toBeVisible()
    await expect(page.getByTestId('list-options')).toHaveCount(0)
  })
})
