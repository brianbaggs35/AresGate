import type { EventRequest } from '../support'
import { expect, test } from '../support'

const ADDRESS = '203.0.113.7'

/** Some events in the last few minutes, and a few from hours before, for the chart to tell apart. */
const SPREAD: EventRequest[] = [
  {
    source: 'opnsense',
    summary: `Blocked tcp from ${ADDRESS}`,
    src_address: ADDRESS,
    src_port: 51234,
    dst_address: '192.168.1.20',
    dst_port: 443,
    protocol: 'tcp',
    seconds_ago: 90,
    repeat: 5,
    every_seconds: 30,
  },
  { source: 'wazuh', kind: 'alert', severity: 'high', summary: 'Old alert', seconds_ago: 18_000 },
]

test.describe('logs on a computer', () => {
  test('are a table, with a heading for the day and a column for each thing worth reading', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SPREAD)

    await logs.goto()

    await expect(logs.table).toBeVisible()
    await expect(logs.cards).toHaveCount(0)
    await expect(logs.table.getByRole('columnheader')).toHaveText([
      'Time',
      'Severity',
      'Source',
      'Kind',
      'From',
      'To',
      'Summary',
    ])
    await expect(logs.days.first()).toHaveText(/^(Today|Yesterday)$/)
    await expect(logs.rows.first()).toContainText(`${ADDRESS}:51234`)
    await expect(logs.rows.first()).toContainText('192.168.1.20:443')
  })

  test('keep the headings in view while the page is scrolled', async ({ harness, logs, page }) => {
    await harness.createEvents([{ summary: 'Blocked udp', repeat: 80, every_seconds: 20 }])
    await logs.goto()
    await expect(logs.rows).toHaveCount(80)
    const heading = logs.table.getByRole('columnheader').first()
    const sticky = await heading.evaluate((cell) => getComputedStyle(cell).position)
    expect(sticky).toBe('sticky')

    await page.evaluate(() => {
      window.scrollTo(0, 1500)
    })

    const box = await heading.boundingBox()
    // Under the top bar, not scrolled away.
    expect(box?.y ?? Number.NaN).toBeGreaterThanOrEqual(0)
    expect(box?.y ?? Number.NaN).toBeLessThan(80)
  })

  test('show the columns that are chosen, and remember them', async ({ harness, logs, page }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()
    const headings = logs.table.getByRole('columnheader')
    await expect(headings).toHaveCount(7)

    await logs.view.click()
    await logs.columnBox('Protocol').check()
    await logs.columnBox('Severity').uncheck()
    await page.keyboard.press('Escape')

    await expect(headings).toHaveText([
      'Time',
      'Source',
      'Kind',
      'From',
      'To',
      'Protocol',
      'Summary',
    ])
    await expect(logs.rows.first().locator('[data-column="protocol"]')).toHaveText('tcp')
    // The time and the summary are never left out.
    await logs.view.click()
    await expect(logs.columnBox('Time')).toBeDisabled()
    await expect(logs.columnBox('Summary')).toBeDisabled()
    await page.keyboard.press('Escape')

    await page.reload()
    await expect(headings).toHaveText([
      'Time',
      'Source',
      'Kind',
      'From',
      'To',
      'Protocol',
      'Summary',
    ])

    await logs.view.click()
    await logs.columnsReset.click()
    await page.keyboard.press('Escape')
    await expect(headings).toHaveCount(7)
    await expect(headings.nth(1)).toHaveText('Severity')
  })

  test('show the time exactly or as how long ago, and remember which', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()
    const time = logs.rows.first().locator('[data-column="time"]')
    await expect(time).toHaveText(/^\d{1,2}:\d{2}:\d{2} [AP]M$/)

    await logs.view.click()
    await logs.timeRelative.click()
    await page.keyboard.press('Escape')

    await expect(time).toHaveText(/ago$|^just now$/)
    await expect(time.locator('time')).toHaveAttribute('title', /\d{4}/)
    await page.reload()
    await expect(logs.rows.first().locator('[data-column="time"]')).toHaveText(/ago$|^just now$/)
  })

  test('are moved through with the arrow keys, and opened with Enter', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()
    await expect(logs.rows).toHaveCount(6)
    const summaries = page.getByTestId('log-open')
    await summaries.first().focus()

    await page.keyboard.press('ArrowDown')
    await expect(summaries.nth(1)).toBeFocused()
    await page.keyboard.press('End')
    await expect(summaries.last()).toBeFocused()
    await page.keyboard.press('Home')
    await expect(summaries.first()).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(summaries.first()).toBeFocused()

    await summaries.nth(2).focus()
    await page.keyboard.press('Enter')

    await expect(logs.drawer).toBeVisible()
    await expect(logs.drawerTitle).toHaveText(`Blocked tcp from ${ADDRESS}`)
  })

  test('mark the row that is open, and give the keyboard back to it afterwards', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()
    const summaries = page.getByTestId('log-open')

    await summaries.nth(1).focus()
    await page.keyboard.press('Enter')
    await expect(logs.drawer).toBeVisible()
    await expect(summaries.nth(1)).toHaveAttribute('aria-current', 'true')

    await page.keyboard.press('Escape')

    await expect(logs.drawer).toBeHidden()
    await expect(summaries.nth(1)).toBeFocused()
  })

  test('are narrowed to a stretch of time by a pick of a bar of the chart', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()
    await expect(logs.events).toHaveCount(6)

    await logs.bars.first().click()

    await expect(page).toHaveURL(/q=since:\S+\+before:\S+|q=before:\S+\+since:\S+/)
    await expect(logs.events).toHaveCount(1)
    await expect(logs.terms).toHaveCount(2)
    await expect(logs.events.first()).toContainText('Old alert')
  })

  test('open the sheet at the side, with the list still beside it', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SPREAD)
    await logs.goto()

    await logs.rows.first().click()

    await expect(logs.drawer).toBeVisible()
    const viewport = page.viewportSize()
    // It slides in from the right, so it is measured once it has arrived.
    await expect
      .poll(async () => {
        const box = await logs.drawer.boundingBox()
        return Math.round((box?.x ?? 0) + (box?.width ?? 0))
      })
      .toBe(viewport?.width)
    const box = await logs.drawer.boundingBox()
    expect(box?.width ?? Number.NaN).toBeLessThanOrEqual(36 * 16 + 1)
    expect(box?.height).toBe(viewport?.height)
  })
})
