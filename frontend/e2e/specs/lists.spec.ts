import type { Locator, Page } from '@playwright/test'

import { expect, expectAccessible, test } from '../support'

/** Opens the panel with the file of the list: its own button on a computer, and on a phone the
 * one menu that holds it and the views. */
async function openExport(page: Page): Promise<Locator> {
  const options = page.getByTestId('list-options')
  if (await options.isVisible()) {
    await options.click()
    return page.getByTestId('list-panel')
  }
  await page.getByTestId('list-export').click()
  return page.getByTestId('export-panel')
}

/** The same for the views. */
async function openViews(page: Page): Promise<Locator> {
  const options = page.getByTestId('list-options')
  if (await options.isVisible()) {
    await options.click()
    return page.getByTestId('list-panel')
  }
  await page.getByTestId('list-views-button').click()
  return page.getByTestId('views-panel')
}

test.describe('lists you can export and keep views of', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createAssets({
      devices: [
        {
          hostname: 'laptop',
          mac: '00:11:22:0a:0b:0c',
          vendor: 'Example Devices Inc.',
          addresses: ['192.168.1.20'],
          listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
        },
        { hostname: 'phone', mac: '02:aa:bb:cc:dd:ee', listed: [{ via: 'dhcp' }] },
      ],
      hosts: [],
    })
  })

  test('downloads what the filters show, in words, in the owner’s time zone', async ({ page }) => {
    await page.goto('/assets?q=laptop')
    const panel = await openExport(page)

    const csv = await page.request.get(
      (await panel.getByTestId('export-csv').getAttribute('href')) as string,
    )
    const json = await page.request.get(
      (await panel.getByTestId('export-json').getAttribute('href')) as string,
    )

    expect(csv.headers()['content-type']).toContain('text/csv')
    expect(csv.headers()['content-disposition']).toContain('attachment')
    const [header, ...rows] = (await csv.text()).trim().split('\r\n')
    expect(header).toContain('Name,Kind,Host name,Maker')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toContain('laptop')
    const asJson = (await json.json()) as Record<string, string>[]
    expect(asJson.map((row) => row.Name)).toEqual(['laptop'])
    expect(asJson[0]?.['First seen']).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$/)
  })

  test('keeps a view, opens the page on it, renames it and forgets it', async ({ page }) => {
    await page.goto('/assets?q=laptop')
    let panel = await openViews(page)
    await expect(panel.getByTestId('views-none')).toBeVisible()

    await panel.getByTestId('view-name').getByRole('textbox').fill('Laptops')
    await panel.getByTestId('view-as-default').getByRole('checkbox').check()
    await panel.getByTestId('view-save').click()

    await expect(panel.getByTestId('views-notice')).toHaveText('Saved as Laptops.')
    await expect(panel.getByTestId('view-use')).toHaveText(/Laptops/)
    await expect(panel.getByTestId('view-default')).toBeVisible()
    await page.keyboard.press('Escape')

    // Opened bare, the page opens on it.
    await page.goto('/assets')
    await expect(page).toHaveURL('/assets?q=laptop')

    // Another page of filters, and a tap on the view brings its filters back.
    await page.goto('/assets?q=phone')
    panel = await openViews(page)
    await panel.getByTestId('view-use').click()
    await expect(page).toHaveURL('/assets?q=laptop')

    await panel.getByTestId('view-rename-start').click()
    await panel.getByTestId('view-rename').getByRole('textbox').fill('My laptops')
    await panel.getByTestId('view-rename-save').click()
    await expect(panel.getByTestId('view-use')).toHaveText(/My laptops/)

    await panel.getByTestId('view-forget').click()
    await expect(panel.getByTestId('views-none')).toBeVisible()
  })

  test('opens a view of a program that is not connected, and says so', async ({ page }) => {
    await page.goto('/assets?source=wazuh')
    let panel = await openViews(page)
    await panel.getByTestId('view-name').getByRole('textbox').fill('Wazuh only')
    await panel.getByTestId('view-save').click()
    await expect(panel.getByTestId('views-notice')).toHaveText('Saved as Wazuh only.')
    await page.keyboard.press('Escape')

    await page.goto('/assets')
    panel = await openViews(page)
    await panel.getByTestId('view-use').click()

    await expect(page).toHaveURL('/assets?source=wazuh')
    await expect(panel.getByTestId('views-notice')).toContainText(
      'not connected any more. It opens anyway',
    )
  })

  test('has nothing axe objects to, with the views open', async ({ page }) => {
    await page.goto('/assets?q=laptop')
    const panel = await openViews(page)
    await panel.getByTestId('view-name').getByRole('textbox').fill('Laptops')
    await panel.getByTestId('view-save').click()
    await expect(panel.getByTestId('view-use')).toBeVisible()

    await expectAccessible(page)
  })
})
