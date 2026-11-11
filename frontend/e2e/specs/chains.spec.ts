import type { IncidentRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

const ATTACKER = '93.184.216.34'
const SERVER = '8.8.4.4'
const DEVICE = '192.168.1.20'

/** An outside address that tried a flaw on the camera, a while ago. */
const BREAK_IN: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['wazuh', 'opnsense'],
  twin: 'opnsense',
  signals: 1,
  exploit: true,
  minutes_ago: 40,
  device: DEVICE,
  device_name: 'Kitchen camera',
}

/** The camera then sending a beacon to a server on the internet. */
const BEACON: IncidentRequest = {
  address: SERVER,
  severity: 'high',
  programs: ['wazuh'],
  signals: 1,
  outbound: true,
  compromise: true,
  minutes_ago: 5,
  device: DEVICE,
}

/** The camera only calling out: nothing about it says it was taken over. */
const CALL: IncidentRequest = { ...BEACON, compromise: false, exploit: true }

test.describe('an attack across two devices', () => {
  test('links an exploit at a device to the device calling out, and says it was seen', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([BREAK_IN, BEACON])

    await page.goto('/threats')
    const card = page.getByTestId('chain-card')
    await expect(card).toHaveCount(1)
    await expect(card.getByTestId('chain-device')).toHaveText(`Kitchen camera (${DEVICE})`)
    await expect(card.getByTestId('chain-summary')).toContainText(
      `${ATTACKER} attacked ${DEVICE}, which then called ${SERVER}.`,
    )
    await expect(card.getByTestId('chain-link')).toHaveText('Seen')

    await card.getByTestId('chain').click()

    await expect(page.getByTestId('page-heading')).toHaveText(
      `Attack on Kitchen camera (${DEVICE})`,
    )
    await expect(page.getByTestId('chain-certainty')).toContainText('Seen, not guessed')
    const steps = page.getByTestId('path-step')
    await expect(steps).toHaveCount(2)
    await expect(steps.nth(0).getByTestId('step-role')).toHaveText('Got in from the internet')
    await expect(steps.nth(1).getByTestId('step-role')).toHaveText('Then the device called out')
    await expect(steps.nth(1).getByTestId('step-link')).toHaveText('Seen')
    await expect(steps.nth(1).getByTestId('step-reason')).toContainText('taken over')
    await expect(page.getByTestId('path-device')).toContainText('Kitchen camera')
    await expect(page.getByTestId('why')).toHaveCount(3)
  })

  test('counts an alert that two programs reported once, and shows who saw it', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([BREAK_IN, BEACON])
    await page.goto('/threats')
    await page.getByTestId('chain').click()

    const first = page.getByTestId('path-step').first()
    await expect(first.getByTestId('step-sources')).toContainText('Wazuh')
    await expect(first.getByTestId('step-duplicates')).toContainText('counted once')
    await expect(first.getByTestId('evidence-agreed').first()).toContainText(
      'Also reported by OPNsense, counted once.',
    )
  })

  test('keeps a link that was only inferred apart from one that was seen', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([BREAK_IN, CALL])
    await page.goto('/threats')

    await expect(page.getByTestId('chain-link')).toHaveText('Inferred')
    await page.getByTestId('chain').click()

    await expect(page.getByTestId('chain-certainty')).toContainText('Part of this is inferred')
    await expect(page.getByTestId('path-step').nth(0)).toHaveAttribute('data-link', 'confirmed')
    await expect(page.getByTestId('path-step').nth(1)).toHaveAttribute('data-link', 'inferred')
    await expect(page.getByTestId('step-reason').nth(1)).toContainText('this link is inferred')
  })

  test('is not made of a scan alone, nor of a device that only called out', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([
      { ...BREAK_IN, exploit: false, scan: true, twin: undefined },
      BEACON,
    ])

    await page.goto('/threats')

    await expect(page.getByTestId('chains')).toHaveCount(0)
  })

  test('says on each incident that it is a step, and leads to the whole attack', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents([BREAK_IN, BEACON])
    await incidents.goto()

    await incidents.cards.filter({ hasText: SERVER }).first().click()

    await expect(page.getByTestId('incident-chain')).toContainText(
      'A step of an attack across two devices',
    )
    await page.getByTestId('incident-chain-open').click()
    await expect(page.getByTestId('chain-certainty')).toBeVisible()
    await page.getByTestId('step-open').first().click()
    await expect(page.getByTestId('incident-chain')).toBeVisible()
  })

  test('fits the screen and passes the accessibility checks', async ({ harness, page }) => {
    await harness.createIncidents([BREAK_IN, BEACON])
    await page.goto('/threats')
    await expect(page.getByTestId('chain-card')).toHaveCount(1)
    await expectAccessible(page)

    await page.getByTestId('chain').click()
    await expect(page.getByTestId('path-step')).toHaveCount(2)
    await expectAccessible(page)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
