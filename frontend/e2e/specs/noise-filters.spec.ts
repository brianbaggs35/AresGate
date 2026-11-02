import { expect, test } from '../support'
import type { IncidentRequest } from '../support/harness'

const REAL: IncidentRequest = {
  address: '93.184.216.34',
  severity: 'high',
  programs: ['wazuh'],
  signals: 2,
}
const DOUBTFUL: IncidentRequest = {
  address: '1.1.1.1',
  severity: 'medium',
  programs: ['wazuh'],
  signals: 2,
}
const FAINT: IncidentRequest = {
  address: '8.8.8.8',
  severity: 'low',
  programs: ['wazuh'],
  signals: 1,
}
// Two devices on the network talking to each other: the harness's attacked device is 192.168.1.x.
const INSIDE: IncidentRequest = {
  address: '192.168.1.77',
  severity: 'high',
  programs: ['wazuh'],
  signals: 2,
}

test.describe('noise filters page', () => {
  test('is one of the settings pages, and has nothing to filter on a new install', async ({
    page,
    settings,
    noiseFilters,
  }) => {
    await settings.goto()

    await settings.noiseFiltersLink.click()

    await expect(page).toHaveURL('/settings/noise-filters')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.noiseFiltersLink).toHaveAttribute('aria-current', 'page')
    await expect(noiseFilters.floorValue).toHaveText('35 out of 100 (medium)')
    await expect(noiseFilters.floorSentence).toContainText('at least 35 sure it is real')
    await expect(noiseFilters.floorReset).toBeHidden()
    await expect(noiseFilters.noSources).toContainText('No program has reported an alert yet')
    await expect(noiseFilters.insideSwitch).not.toBeChecked()
    await expect(noiseFilters.effectIdle).toContainText('Change something above')
    await expect(noiseFilters.save).toBeDisabled()
    await expect(noiseFilters.manageVerdicts).toHaveText('Manage your 0 verdicts')
    await noiseFilters.manageVerdicts.click()
    await expect(page).toHaveURL('/settings/verdicts')
  })

  test('lists each program that reported, with what it sent this week', async ({
    harness,
    noiseFilters,
  }) => {
    await harness.createIncidents([REAL, DOUBTFUL, FAINT])

    await noiseFilters.goto()

    await expect(noiseFilters.sources).toHaveCount(1)
    await expect(noiseFilters.source('Wazuh')).toContainText(
      'Last 7 days: 1 high, 3 medium, 1 low.',
    )
  })

  test('says what a different floor would do before it is kept, and keeps it when saved', async ({
    harness,
    noiseFilters,
    page,
  }) => {
    await harness.createIncidents([REAL, DOUBTFUL, FAINT])
    await noiseFilters.goto()

    await noiseFilters.floorSlider.focus()
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('ArrowRight')

    await expect(noiseFilters.floorValue).toHaveText('45 out of 100 (medium)')
    await expect(noiseFilters.floorReset).toHaveText('Back to 35')
    await expect(noiseFilters.effectSentence).toHaveText(
      'With these settings 0 incidents would need you instead of 1, and 0 alerts would be set aside.',
    )
    await expect(noiseFilters.figure('needs-you').now).toHaveText('1')
    await expect(noiseFilters.figure('needs-you').after).toHaveText('0')
    await expect(noiseFilters.figure('filtered-out').now).toHaveText('2')
    await expect(noiseFilters.figure('filtered-out').after).toHaveText('3')

    await noiseFilters.save.click()

    await expect(noiseFilters.saved).toBeVisible()
    await expect(noiseFilters.save).toBeDisabled()
    await noiseFilters.goto()
    await expect(noiseFilters.floorValue).toHaveText('45 out of 100 (medium)')
  })

  test('puts the page back to what is kept', async ({ noiseFilters, page }) => {
    await noiseFilters.goto()
    await noiseFilters.floorSlider.focus()
    await page.keyboard.press('ArrowLeft')
    await expect(noiseFilters.floorValue).toHaveText('30 out of 100 (low)')

    await noiseFilters.discard.click()

    await expect(noiseFilters.floorValue).toHaveText('35 out of 100 (medium)')
    await expect(noiseFilters.save).toBeDisabled()
  })

  test('sets aside what a program reports under the severity it is asked for, and says so on the incident', async ({
    harness,
    noiseFilters,
    incidents,
    incident,
  }) => {
    await harness.createIncidents([REAL, DOUBTFUL, FAINT])
    await noiseFilters.goto()

    await noiseFilters.chooseFloor('Wazuh', 'High and up')

    await expect(noiseFilters.figure('set-aside').now).toHaveText('0')
    await expect(noiseFilters.figure('set-aside').after).toHaveText('4')
    await expect(noiseFilters.figure('needs-you').after).toHaveText('1')
    await noiseFilters.save.click()
    await expect(noiseFilters.saved).toBeVisible()

    await noiseFilters.goto()
    await expect(noiseFilters.source('Wazuh').getByTestId('source-floor')).toContainText(
      'High and up',
    )
    await incidents.goto('?address=1.1.1.1')
    await incidents.cards.first().click()
    await expect(incident.signals).toHaveCount(2)
    await expect(incident.signals.getByTestId('signal-filtered')).toHaveText([
      "Set aside: under this program's severity",
      "Set aside: under this program's severity",
    ])
    await expect(incident.standing).toContainText('Every signal in it was left out')
  })

  test('sets aside alerts between two devices on the network when asked', async ({
    harness,
    noiseFilters,
    incidents,
    incident,
  }) => {
    await harness.createIncidents([REAL, INSIDE])
    await noiseFilters.goto()

    await noiseFilters.insideSwitch.check()

    await expect(noiseFilters.figure('set-aside').after).toHaveText('2')
    await expect(noiseFilters.figure('needs-you').now).toHaveText('2')
    await expect(noiseFilters.figure('needs-you').after).toHaveText('1')
    await noiseFilters.save.click()
    await expect(noiseFilters.saved).toBeVisible()

    await incidents.goto('?address=192.168.1.77')
    await incidents.cards.first().click()
    await expect(incident.signals.getByTestId('signal-filtered')).toHaveText([
      'Set aside: inside your network',
      'Set aside: inside your network',
    ])
  })

  test('says why it could not be worked out when it cannot reach AresGate', async ({
    noiseFilters,
    page,
  }) => {
    await noiseFilters.goto()
    await page.route('**/api/noise-filters/preview', (route) => route.abort())

    await noiseFilters.insideSwitch.check()

    await expect(noiseFilters.failure).toContainText("Can't reach AresGate")
    await expect(noiseFilters.effectIdle).toContainText("It couldn't be worked out")
  })
})
