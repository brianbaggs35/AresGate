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

  test('answers, and suggests what to do: a button to open the incident, and a proposal to start on it, which can be taken back', async ({
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
    await expect(assistantPanel.actions).toHaveText([/Open incident/i])
    await expect(assistantPanel.proposals).toContainText(/Start investigating incident/i)
    await expect(assistantPanel.proposals).toContainText('Changes this incident only.')

    // Nothing changes until it is approved; approving is a change the owner made, and can be taken
    // back.
    await expect(incident.status).toHaveText('Open')
    await assistantPanel.approve.click()
    await expect(assistantPanel.done).toContainText('Approved. 1 incident changed.')
    await assistantPanel.undo.click()
    await expect(assistantPanel.undone).toBeVisible()
    await page.reload()
    await expect(incident.status).toHaveText('Open')

    // Approved again and not taken back, it stays.
    await assistantPanel.opener.click()
    await assistantPanel.ask('What needs my attention right now?')
    await assistantPanel.approve.click()
    await expect(assistantPanel.done).toBeVisible()
    await page.reload()
    await expect(incident.status).toHaveText('Investigating')
  })

  test('changes nothing when a proposal is denied', async ({
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

    await assistantPanel.deny.click()

    await expect(assistantPanel.denied).toHaveText('Denied. Nothing was changed.')
    await expect(assistantPanel.approve).toHaveCount(0)
    await page.reload()
    await expect(incident.status).toHaveText('Open')
  })

  test('proposes dismissing several incidents together, and dismisses them all when approved', async ({
    harness,
    aiSettings,
    assistantPanel,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN, { ...SCAN, address: '151.101.1.69' }])
    await turnOnAi(harness, aiSettings)
    await page.goto('/')
    await assistantPanel.opener.click()

    await assistantPanel.ask('Please dismiss the background noise.')

    await expect(assistantPanel.proposals).toContainText('Dismiss 2 incidents')
    await expect(assistantPanel.proposals).toContainText('Changes these 2 incidents.')
    await assistantPanel.approve.click()
    await expect(assistantPanel.done).toContainText('Approved. 2 incidents changed.')

    for (const address of [ATTACKER, '151.101.1.69']) {
      await page.goto('/incidents?view=all')
      await page.getByTestId('incident').filter({ hasText: address }).click()
      await expect(page).toHaveURL(/\/incidents\/\d+$/)
      await expect(incident.status).toHaveText('Dismissed')
    }
  })

  test('offers to give a status to the earlier incidents about the same address, and says how many', async ({
    harness,
    aiSettings,
    assistantPanel,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)
    await assistantPanel.opener.click()
    await assistantPanel.ask('What needs my attention right now?')

    await page.getByTestId('proposal-earlier').getByRole('checkbox').check()

    await expect(page.getByTestId('proposal-look')).toHaveText(
      '1 incident in all, and 1 would change.',
    )
    await expect(assistantPanel.proposals).toContainText(
      `Changes every incident about ${ATTACKER}, earlier ones too.`,
    )
    await assistantPanel.approve.click()
    await expect(assistantPanel.done).toContainText('Approved. 1 incident changed.')
  })

  test('proposes a verdict that is remembered for everything about the address', async ({
    harness,
    aiSettings,
    assistantPanel,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await page.goto('/')
    await assistantPanel.opener.click()

    await assistantPanel.ask('That is my printer, it does that every day.')

    await expect(assistantPanel.proposals).toContainText('not suspicious')
    await expect(assistantPanel.proposals).toContainText('Why: Your printer')
    await expect(assistantPanel.proposals).toContainText(`everything about ${ATTACKER}`)
    await assistantPanel.approve.click()
    await expect(assistantPanel.done).toContainText('Approved. Remembered 1 verdict')
    await page.goto('/settings/verdicts')
    await expect(page.getByTestId('verdict-about')).toContainText(ATTACKER)
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
