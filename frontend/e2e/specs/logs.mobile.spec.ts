import type { EventRequest } from '../support'
import { expect, test, waitForMotion } from '../support'

const ADDRESS = '203.0.113.7'

const SOME: EventRequest[] = [
  {
    source: 'opnsense',
    summary: `Blocked tcp from ${ADDRESS}`,
    src_address: ADDRESS,
    src_port: 51234,
    dst_address: '192.168.1.20',
    dst_port: 443,
    protocol: 'tcp',
    seconds_ago: 90,
    raw: {
      action: 'block',
      interface: 'wan',
      note: 'a long line of text in the record that has no place to break except at the edge',
    },
  },
  {
    source: 'wazuh',
    kind: 'alert',
    severity: 'high',
    summary: 'Failed login',
    seconds_ago: 18_000,
  },
]

test.describe('logs on a phone', () => {
  test('are cards, one for each event, with no table and no column menu', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SOME)

    await logs.goto()

    await expect(logs.cards).toHaveCount(2)
    await expect(logs.table).toHaveCount(0)
    await expect(logs.view).toHaveCount(0)
    await expect(logs.cards.first()).toContainText('OPNsense · firewall')
    await expect(logs.cards.first()).toContainText(`${ADDRESS}:51234 → 192.168.1.20:443`)
    await expect(logs.cards.first()).toContainText(/minutes? ago|just now/)
    await expect(logs.cards.last()).toContainText('High')
  })

  test('fit the screen, with the cards the width of it', async ({ harness, logs, page }) => {
    await harness.createEvents(SOME)
    await logs.goto()
    await expect(logs.cards).toHaveCount(2)

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    const viewport = page.viewportSize()
    const card = await logs.cards.first().boundingBox()
    expect(card?.width ?? 0).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
    // Big enough to put a thumb on.
    expect(card?.height ?? 0).toBeGreaterThanOrEqual(48)
  })

  test('open one in a sheet that fills the screen, with the record wrapped to fit it', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    await logs.cards.first().tap()

    await expect(logs.drawer).toBeVisible()
    await waitForMotion(page)
    const viewport = page.viewportSize()
    const box = await logs.drawer.boundingBox()
    expect(box?.width).toBeCloseTo(viewport?.width ?? 0, 0)
    expect(box?.height).toBeCloseTo(viewport?.height ?? 0, 0)
    await expect(logs.rawText).toContainText('"interface": "wan"')
    const raw = await logs.rawText.boundingBox()
    expect((raw?.x ?? 0) + (raw?.width ?? 0)).toBeLessThanOrEqual((viewport?.width ?? 0) + 1)
    const overflow = await logs.drawer.evaluate((sheet) => {
      const body = sheet.querySelector('.log-drawer__body') as HTMLElement
      return body.scrollWidth - body.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(0)

    await logs.drawerClose.tap()

    await expect(logs.drawer).toBeHidden()
  })

  test('are narrowed to a stretch of time by the second tap on a bar', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()
    await expect(logs.cards).toHaveCount(2)

    // The first tap reads the bar, and the second picks it.
    await logs.bars.first().tap()
    await expect(page).toHaveURL('/logs')
    await logs.bars.first().tap()

    await expect(page).toHaveURL(/q=/)
    await expect(logs.cards).toHaveCount(1)
    await expect(logs.cards.first()).toContainText('Failed login')
  })

  test('are reached from the bottom bar, where Logs is one of the places', async ({
    page,
    shell,
    logs,
  }) => {
    await page.goto('/')

    await shell.logsLink.tap()

    await expect(page).toHaveURL('/logs')
    await expect(logs.heading).toHaveText('Logs')
    await shell.expectCurrent('logs')
  })
})
