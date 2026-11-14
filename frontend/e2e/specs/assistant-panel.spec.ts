import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, expectAccessible, test, turnOnAi } from '../support'

const ATTACKER = '93.184.216.34'

/** A scan that two programs saw. */
const SCAN: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 4,
}

async function openIncident(page: Page): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('the assistant panel', () => {
  test('opens over any page, knows which one, and puts the box in focus', async ({
    harness,
    aiSettings,
    assistantPanel,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)

    await expect(assistantPanel.panel).toBeHidden()
    await assistantPanel.opener.click()

    await expect(assistantPanel.panel).toBeVisible()
    await expect(assistantPanel.context).toContainText('Looking at incident')
    await expect(assistantPanel.starters.first()).toContainText('this incident')
    await expect(assistantPanel.input).toBeFocused()
    // The page is still where it was.
    await expect(page).toHaveURL(/\/incidents\/\d+$/)

    await assistantPanel.close.click()
    await expect(assistantPanel.panel).toBeHidden()
  })

  test('answers, and suggests what to do as buttons: open the incident, or start on it, and take that back', async ({
    harness,
    aiSettings,
    assistantPanel,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)
    await assistantPanel.opener.click()

    await assistantPanel.ask('What needs my attention right now?')

    await expect(assistantPanel.answers).toContainText('Start with incident')
    await expect(assistantPanel.actions).toHaveText(
      ['Open incident', 'Start investigating incident'].map((label) => new RegExp(label)),
    )

    // Nothing changes until a button is pressed; pressing is a change the owner made, and can be
    // taken back.
    await assistantPanel.actions.nth(1).click()
    await expect(assistantPanel.done).toBeVisible()
    await page.reload()
    await expect(incident.status).toHaveText('Investigating')

    await assistantPanel.opener.click()
    await assistantPanel.ask('What needs my attention right now?')
    await assistantPanel.actions.nth(1).click()
    await expect(assistantPanel.done).toBeVisible()
    await assistantPanel.undo.click()
    await expect(assistantPanel.undone).toBeVisible()
    await page.reload()
    await expect(incident.status).toHaveText('Investigating')
  })

  test('carries the conversation to the Assistant page', async ({
    harness,
    aiSettings,
    assistantPanel,
    assistant,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await page.goto('/')
    await assistantPanel.opener.click()
    await assistantPanel.ask('What needs my attention right now?')
    await expect(assistantPanel.answers).toContainText('Start with incident')

    await assistantPanel.full.click()

    await expect(page).toHaveURL(/\/assistant\/\d+$/)
    await expect(assistant.answers).toContainText('Start with incident')
    await expect(assistantPanel.panel).toBeHidden()
    // The Assistant page is the conversation, so there is no panel to open from it.
    await expect(assistantPanel.opener).toHaveCount(0)
  })

  test('has no WCAG 2.2 AA problems', async ({ harness, aiSettings, assistantPanel, page }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await page.goto('/')
    await assistantPanel.opener.click()
    await assistantPanel.ask('What needs my attention right now?')
    await expect(assistantPanel.answers).toContainText('Start with incident')

    await expectAccessible(page)
  })
})
