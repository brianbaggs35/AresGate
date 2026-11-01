import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

const ATTACKER = '93.184.216.34'

/** A scan that two programs saw, of a device on the network that is known by name. */
const SCAN: IncidentRequest = {
  address: ATTACKER,
  severity: 'medium',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 4,
  device_name: 'nas',
}

async function openIncident(page: Page): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('what the AI makes of an incident', () => {
  test('says it has not read one, and reads it when asked', async ({
    harness,
    aiSettings,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)

    await openIncident(page)
    await expect(incident.aiUnread).toContainText('The AI has not read this incident')
    await incident.aiAsk.click()

    await expect(incident.aiClass).toHaveText('Probe')
    await expect(incident.aiConfidence).toHaveText('90 of 100 sure')
    await expect(incident.aiHeadline).toContainText('scanned one device')
    await expect(incident.aiChecks).toHaveCount(1)
    // The AI was shown a stand-in for the device, and the page shows the device it stood for.
    await expect(incident.aiStory).not.toContainText('HOST_')
    await expect(incident.aiStory).toContainText('192.168.')
    await expect(incident.aiSource).toContainText('Read by Anthropic (claude-haiku-5-5)')
    await expect(incident.aiChip).toHaveText('AI: Probe, 90% sure')
    await expect(incident.aiBusy).toHaveCount(0)
  })

  test('reads an incident when you start investigating it', async ({
    harness,
    aiSettings,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)

    await incident.action('investigating').click()

    await expect(incident.notice).toHaveText('Marked as investigating.')
    await expect(incident.aiClass).toHaveText('Probe')
    await expect(incident.status).toHaveText('Investigating')
  })

  test('says plainly that AI is off, and where to turn it on', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await openIncident(page)

    await incident.action('investigating').click()

    await expect(incident.status).toHaveText('Investigating')
    await expect(incident.aiFailure).toContainText('AI is turned off.')
    await incident.aiSettingsLink.click()
    await expect(page).toHaveURL('/settings/ai')
  })

  test('gives the verdict the AI suggests when you say so, and never before', async ({
    harness,
    aiSettings,
    incident,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)
    await incident.aiAsk.click()
    await expect(incident.aiSuggestion).toContainText('Low priority')
    await expect(incident.verdictChip).toHaveCount(0)

    await expect(incident.aiAccept).toHaveText(`Mark ${ATTACKER} as low priority`)
    await incident.aiAccept.click()

    await expect(incident.aiNotice).toContainText(`${ATTACKER} is low priority`)
    await expect(incident.verdictChip).toHaveText('Low priority')
    await expect(incident.aiSuggestion).toHaveCount(0)
  })

  test('shows its word for an incident in the list', async ({
    harness,
    aiSettings,
    incident,
    incidents,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)
    await incident.aiAsk.click()
    await expect(incident.aiClass).toHaveText('Probe')

    await incidents.goto('?view=all')

    await expect(page.getByTestId('ai-chip')).toHaveText('AI: Probe, 90% sure')
  })

  test('puts the reading in the activity log', async ({
    harness,
    aiSettings,
    incident,
    activity,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await openIncident(page)
    await incident.aiAsk.click()
    await expect(incident.aiClass).toHaveText('Probe')

    await activity.goto()

    await expect(activity.entries.first()).toContainText('The AI was asked about an incident')
  })
})
