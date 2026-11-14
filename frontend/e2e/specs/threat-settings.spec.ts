import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

/** A real attack, an address that is only a maybe, and a bot sweeping the network: one threat, one
 * suspect and one thing in the background. */
const ATTACK: IncidentRequest = {
  address: '93.184.216.34',
  severity: 'critical',
  programs: ['wazuh'],
  signals: 3,
  exploit: true,
  compromise: true,
  minutes_ago: 8,
}
const MAYBE: IncidentRequest = {
  address: '1.1.1.1',
  severity: 'high',
  programs: ['wazuh'],
  signals: 2,
  minutes_ago: 20,
}
const SWEEP: IncidentRequest = {
  address: '8.8.4.10',
  severity: 'low',
  programs: ['opnsense'],
  signals: 6,
  scan: true,
  neighbours: 2,
  waves: 2,
  ports: [22, 80, 443],
  minutes_ago: 30,
}

test.describe('the threat detection settings', () => {
  test('are one of the settings pages, and start at what AresGate does with no tuning', async ({
    page,
    settings,
    threatSettings,
  }) => {
    await settings.goto()

    await settings.threatDetectionLink.click()

    await expect(page).toHaveURL('/settings/threat-detection')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.threatDetectionLink).toHaveAttribute('aria-current', 'page')
    await expect(threatSettings.levelValue).toHaveText('65 out of 100')
    await expect(threatSettings.levelReset).toBeHidden()
    await expect(threatSettings.levelSentence).toContainText('The usual')
    await expect(threatSettings.aiOff).toContainText('No AI is watching')
    await expect(threatSettings.effectIdle).toContainText('Change something above')
    await expect(threatSettings.save).toBeDisabled()
  })

  test('say what a different bar would do before it is kept, and keep it when saved', async ({
    harness,
    threatSettings,
    page,
  }) => {
    await harness.createIncidents([ATTACK, MAYBE, SWEEP])
    await threatSettings.goto()

    await threatSettings.levelSlider.focus()
    // Five steps down, to where the maybe is sure enough.
    for (let step = 0; step < 5; step++) await page.keyboard.press('ArrowLeft')

    await expect(threatSettings.levelValue).toHaveText('40 out of 100')
    await expect(threatSettings.levelReset).toHaveText('Back to 65')
    await expect(threatSettings.levelSentence).toContainText('Lower than usual')
    await expect(threatSettings.effectTable).toBeVisible()
    await expect(threatSettings.figure('threats').now).toHaveText('1')
    await expect(threatSettings.figure('threats').after).toHaveText('2')
    await expect(threatSettings.figure('suspects').now).toHaveText('1')
    await expect(threatSettings.figure('suspects').after).toHaveText('0')
    await expect(threatSettings.effectSentence).toHaveText(
      'Saving would change the lanes by +1 threat, −1 suspect.',
    )

    await threatSettings.save.click()

    await expect(threatSettings.saved).toBeVisible()
    await expect(threatSettings.save).toBeDisabled()
    await threatSettings.goto()
    await expect(threatSettings.levelValue).toHaveText('40 out of 100')
  })

  test('say how far the devices that matter move the bar, and keep it when saved', async ({
    threatSettings,
    page,
  }) => {
    await threatSettings.goto()
    await expect(threatSettings.dropValue).toHaveText('Important devices: 10 points lower')
    await expect(threatSettings.raiseValue).toHaveText('Guests and IoT devices: 0 points higher')

    await threatSettings.dropSlider.focus()
    await page.keyboard.press('ArrowRight')
    await threatSettings.raiseSlider.focus()
    for (let step = 0; step < 5; step++) await page.keyboard.press('ArrowRight')

    await expect(threatSettings.dropValue).toHaveText('Important devices: 11 points lower')
    await expect(threatSettings.raiseValue).toHaveText('Guests and IoT devices: 5 points higher')
    await expect(threatSettings.save).toBeEnabled()
    await threatSettings.save.click()
    await expect(threatSettings.saved).toBeVisible()

    await threatSettings.goto()
    await expect(threatSettings.dropValue).toHaveText('Important devices: 11 points lower')
    await expect(threatSettings.raiseValue).toHaveText('Guests and IoT devices: 5 points higher')
  })

  test('keep the AI from giving verdicts until it is allowed to, and keep what is chosen', async ({
    threatSettings,
  }) => {
    await threatSettings.goto()
    await expect(threatSettings.verdictsSwitch).not.toBeChecked()

    await threatSettings.verdictsSwitch.check()
    await threatSettings.save.click()
    await expect(threatSettings.saved).toBeVisible()

    await threatSettings.goto()
    await expect(threatSettings.verdictsSwitch).toBeChecked()
  })

  test('put the page back to what is kept', async ({ threatSettings, page }) => {
    await threatSettings.goto()
    await threatSettings.levelSlider.focus()
    await page.keyboard.press('ArrowLeft')
    await expect(threatSettings.levelValue).toHaveText('60 out of 100')

    await threatSettings.discard.click()

    await expect(threatSettings.levelValue).toHaveText('65 out of 100')
    await expect(threatSettings.save).toBeDisabled()
  })

  test('go back to the usual bar with one click', async ({ threatSettings, page }) => {
    await threatSettings.goto()
    await threatSettings.levelSlider.focus()
    await page.keyboard.press('ArrowRight')
    await expect(threatSettings.levelValue).toHaveText('70 out of 100')

    await threatSettings.levelReset.click()

    await expect(threatSettings.levelValue).toHaveText('65 out of 100')
    await expect(threatSettings.levelReset).toBeHidden()
  })

  test('take what is open to the internet, and what the network is for, in your words', async ({
    threatSettings,
  }) => {
    await threatSettings.goto()

    await threatSettings.exposure('some').check()
    await threatSettings.ports.fill('22, 443, 51820')
    await threatSettings.notes.fill('A Plex server and a VPN to the office.')
    await expect(threatSettings.save).toBeEnabled()
    await threatSettings.save.click()

    await expect(threatSettings.saved).toBeVisible()
    await threatSettings.goto()
    await expect(threatSettings.exposure('some')).toBeChecked()
    await expect(threatSettings.ports).toHaveValue('22, 443, 51820')
    await expect(threatSettings.notes).toHaveValue('A Plex server and a VPN to the office.')
  })

  test('refuse a port that is not one, and say which', async ({ threatSettings }) => {
    await threatSettings.goto()

    await threatSettings.exposure('some').check()
    await threatSettings.ports.fill('22, https')

    await expect(threatSettings.portsError).toContainText('https is not a port number')
    await threatSettings.ports.fill('22, 443')
    await expect(threatSettings.portsError).not.toContainText('port number')
  })

  test('hide the bar for the AI until it may set things aside', async ({ threatSettings }) => {
    await threatSettings.goto()
    await expect(threatSettings.clearBar).toBeVisible()
    await expect(threatSettings.clearValue).toHaveText('80% sure')

    await threatSettings.clearSwitch.uncheck()

    await expect(threatSettings.clearBar).toBeHidden()
    await expect(threatSettings.save).toBeEnabled()
    await threatSettings.save.click()
    await expect(threatSettings.saved).toBeVisible()
    await threatSettings.goto()
    await expect(threatSettings.clearSwitch).not.toBeChecked()
  })

  test('say so, and try again, when they cannot load', async ({ threatSettings, page }) => {
    await page.route('**/api/threat-settings', (route) => route.abort())

    await threatSettings.goto()

    await expect(page.getByTestId('threat-settings-error')).toBeVisible()
    await page.unroute('**/api/threat-settings')
    await page.getByTestId('retry').click()
    await expect(threatSettings.levelValue).toBeVisible()
  })
})
