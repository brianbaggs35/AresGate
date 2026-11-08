import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'
const BOT = '8.8.4.10'
const PROBER = '1.1.1.1'

/** An address that scanned, tried a flaw and then was heard from by a device it got into: the one
 * attack in this set that is real, seen twice over by two programs. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  severity: 'critical',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  exploit: true,
  compromise: true,
  minutes_ago: 6,
  device_name: 'nas',
}

/** A bot that swept the network in waves, as all of the internet does all day. */
const SWEEP: IncidentRequest = {
  address: BOT,
  severity: 'low',
  programs: ['opnsense'],
  signals: 9,
  scan: true,
  neighbours: 2,
  waves: 3,
  ports: [22, 80, 443],
  minutes_ago: 30,
}

/** One probe, reported by two programs that each said the same thing. */
const PROBE: IncidentRequest = {
  address: PROBER,
  severity: 'low',
  programs: ['wazuh'],
  twin: 'ntopng',
  signals: 3,
  scan: true,
  minutes_ago: 50,
}

test.describe('the threats page', () => {
  test('is in the menu, and says nothing has been reported on a new install', async ({
    page,
    shell,
    threats,
  }) => {
    await page.goto('/')

    await shell.threatsLink.click()

    await expect(page).toHaveURL('/threats')
    await expect(page).toHaveTitle('Threats · AresGate')
    await expect(threats.heading).toHaveText('Threats')
    await expect(shell.threatsLink).toHaveAttribute('aria-current', 'page')
    await expect(threats.funnelSentence).toContainText('No program reported anything')
    await expect(threats.count('threat')).toHaveText('0')
    await expect(threats.count('suspect')).toHaveText('0')
    await expect(threats.count('background')).toHaveText('0')
    // With nothing in the first two lanes the page opens on the background, which is empty too.
    await expect(threats.lane('background')).toHaveClass(/v-btn--active/)
    await expect(threats.kindsEmpty).toContainText('Nothing in the background')
    await expect(threats.coverage).toHaveText('There are no kinds of incident to judge.')
  })

  test('puts a real attack in Threats, with how far it got', async ({ harness, threats, page }) => {
    await harness.createIncidents([ATTACK, SWEEP, PROBE])

    await threats.goto()

    await expect(threats.lane('threat')).toHaveClass(/v-btn--active/)
    await expect(threats.count('threat')).toHaveText('1')
    await expect(threats.cards).toHaveCount(1)
    await expect(threats.cards.first()).toContainText(ATTACKER)
    await expect(threats.cards.first().getByTestId('lane-chip')).toHaveText('Threat')
    await expect(threats.laneMeaning).toContainText('Highly likely to be a real attack')

    await threats.cards.first().getByTestId('incident').click()

    // The page of the incident says how far it got, and why it is a threat.
    await expect(page).toHaveURL(/\/incidents\/\d+$/)
    const where = page.getByTestId('where-card')
    await expect(where.getByTestId('lane-chip')).toHaveText('Threat')
    await expect(where.getByTestId('stage-trail')).toBeVisible()
    await expect(where.getByTestId('stage-foothold')).toBeVisible()
    await expect(where.getByTestId('where-why').first()).toBeVisible()
  })

  test('counts what two programs both said once, and says where the reports went', async ({
    harness,
    threats,
  }) => {
    await harness.createIncidents([ATTACK, SWEEP, PROBE])

    await threats.goto()

    // The probe's three alerts were said again by a second program, which is not three more.
    await expect(threats.stepCount('reports')).not.toHaveText('0')
    const reports = Number(await threats.stepCount('reports').innerText())
    const alerts = Number(await threats.stepCount('alerts').innerText())
    expect(reports).toBeGreaterThan(alerts)
    await expect(threats.step('alerts')).toContainText(
      '3 were another program saying the same thing',
    )
    await expect(threats.stepCount('incidents')).toHaveText('3')
    await expect(threats.funnelSentence).toContainText('grouped into 3 incidents')
  })

  test('keeps the scanning in the background, grouped into the kinds it is made of', async ({
    harness,
    threats,
    page,
  }) => {
    await harness.createIncidents([ATTACK, SWEEP, PROBE])
    await threats.goto()

    await threats.lane('background').click()

    await expect(page).toHaveURL(/\/threats\?lane=background/)
    await expect(threats.lane('background')).toHaveClass(/v-btn--active/)
    await expect(threats.kinds.first()).toBeVisible()
    await expect(threats.cards).toHaveCount(0)
    await expect(threats.laneMeaning).toContainText('Scanning and probing')
    await threats.backgroundIncidents.click()
    await expect(page).toHaveURL(/\/incidents\?lane=background/)
  })

  test('opens on the lane in its address, and shows the suspects as incidents', async ({
    harness,
    threats,
  }) => {
    await harness.createIncidents([ATTACK, SWEEP, PROBE])

    await threats.goto('suspect')

    await expect(threats.lane('suspect')).toHaveClass(/v-btn--active/)
    await expect(threats.laneMeaning).toContainText('Could be real')
  })

  test('changes how far back it looks, and goes to the settings and the kinds', async ({
    harness,
    threats,
    page,
  }) => {
    await harness.createIncidents([ATTACK])
    await threats.goto()

    await threats.range7.click()

    await expect(threats.range7).toHaveClass(/v-btn--active/)
    await expect(threats.funnelSentence).toContainText('the last 7 days')
    await threats.kindsLink.click()
    await expect(page).toHaveURL('/threats/kinds')
    await page.goBack()
    await threats.tuneLink.click()
    await expect(page).toHaveURL('/settings/threat-detection')
  })

  test('says so, and tries again, when it cannot load', async ({ threats, page }) => {
    await page.route('**/api/threats/overview*', (route) => route.abort())

    await threats.goto()

    await expect(threats.error).toBeVisible()
    await page.unroute('**/api/threats/overview*')
    await threats.error.getByRole('button', { name: /try again/i }).click()
    await expect(threats.error).toBeHidden()
    await expect(threats.funnelSentence).toBeVisible()
  })
})
