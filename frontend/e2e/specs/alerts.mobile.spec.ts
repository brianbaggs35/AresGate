import type { Page } from '@playwright/test'

import { expect, test } from '../support'

const ADDRESS =
  'https://discord.com/api/webhooks/1234567890123456789/Zk3-_abcdefghijklmnopqrstuvwxyz0123456789'

async function overflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

test.describe('alerts on a phone', () => {
  test('the card of a channel fits the screen, with all its buttons', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')

    await expect(card).toBeVisible()
    for (const button of ['test', 'sample', 'rules-edit', 'edit', 'remove']) {
      await expect(card.getByTestId(`destination-${button}`)).toBeVisible()
    }
    expect(await overflow(page)).toBeLessThanOrEqual(0)
  })

  test('the sheet shows the three cards, the message as Discord will, and fits the screen', async ({
    alerts,
    page,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)

    await alerts.openRules('Security')

    await expect(alerts.purposes).toBeVisible()
    await expect(alerts.purposeChosen('threats')).toBeChecked()
    await alerts.purpose('custom').scrollIntoViewIfNeeded()
    await expect(alerts.purpose('custom')).toBeVisible()
    await expect(alerts.discord).toBeVisible()
    await expect(alerts.discordTitle).toBeVisible()
    expect(await overflow(page)).toBeLessThanOrEqual(0)
    const sheet = await alerts.rules.boundingBox()
    const embed = await page.getByTestId('discord-embed').boundingBox()
    expect(embed!.x + embed!.width).toBeLessThanOrEqual(sheet!.x + sheet!.width)
  })

  test('choosing a card on a phone changes the message', async ({ alerts }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')
    await expect(alerts.discordFields).toBeVisible()

    await alerts.purpose('serious').click()

    await expect(alerts.purposeChosen('serious')).toBeChecked()
    await expect(alerts.discordFields).toHaveCount(0)
    await expect(alerts.severity).toBeVisible()
  })
})
