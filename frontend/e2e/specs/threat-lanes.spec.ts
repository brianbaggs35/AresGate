import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

const ATTACKER = '93.184.216.34'
const MAYBE_ADDRESS = '1.1.1.1'
const BOT = '8.8.4.10'

/** An address that scanned, tried a flaw and then was heard from by a device it got into. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  severity: 'critical',
  programs: ['wazuh'],
  signals: 3,
  exploit: true,
  compromise: true,
  minutes_ago: 8,
}

/** An address that only might be a threat: one program, a few brute force alerts. */
const MAYBE: IncidentRequest = {
  address: MAYBE_ADDRESS,
  severity: 'high',
  programs: ['wazuh'],
  signals: 2,
  minutes_ago: 20,
}

/** A bot that swept the network, as the internet does all day. */
const SWEEP: IncidentRequest = {
  address: BOT,
  severity: 'low',
  programs: ['opnsense'],
  signals: 6,
  scan: true,
  neighbours: 2,
  waves: 2,
  ports: [22, 80, 443],
  minutes_ago: 30,
}

test.describe('threats, suspects and background', () => {
  test('narrow the incidents to one lane, and name the lane on each', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents([ATTACK, MAYBE, SWEEP])

    await incidents.goto('?lane=suspect')

    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.cards.first()).toContainText(MAYBE_ADDRESS)
    await expect(incidents.cards.first().getByTestId('lane-chip')).toHaveText('Suspect')

    await incidents.choose(incidents.lane, 'Background')

    await expect(page).toHaveURL(/lane=background/)
    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.cards.first().getByTestId('lane-chip')).toHaveText('Background')

    await incidents.choose(incidents.lane, 'Any lane')

    await expect(incidents.cards).toHaveCount(3)
    await expect(incidents.cards.first().getByTestId('lane-chip')).toHaveText('Threat')
  })

  test('count an alert that two programs reported once, and say so on the incident', async ({
    harness,
    incidents,
    incident,
    page,
  }) => {
    await harness.createIncidents([
      {
        address: MAYBE_ADDRESS,
        severity: 'medium',
        programs: ['wazuh'],
        twin: 'ntopng',
        signals: 3,
        scan: true,
        minutes_ago: 10,
      },
    ])
    await incidents.goto()

    // The card counts the three alerts, and says three more were the same thing seen again.
    await expect(incidents.cards.first().getByTestId('incident-signals')).toContainText('3 signals')
    await expect(incidents.cards.first().getByTestId('incident-duplicates')).toContainText(
      '3 also reported',
    )
    await incidents.cards.first().click()

    await expect(incident.signals).toHaveCount(6)
    await expect(incident.signals.getByTestId('signal-duplicate')).toHaveCount(3)
    await expect(page.getByTestId('occurrences-card')).toBeVisible()
    await expect(page.getByTestId('occurrence-duplicates').first()).toContainText(
      'also reported by another program, counted once',
    )
  })

  test('let the AI set a kind of incident aside, and say how many it set aside', async ({
    harness,
    aiSettings,
    threats,
    kinds,
    kind,
    dashboard,
  }) => {
    await harness.createIncidents([MAYBE])
    await turnOnAi(harness, aiSettings)
    await threats.goto('suspect')
    await expect(threats.cards).toHaveCount(1)

    // The AI is asked once about the kind, and what it says covers every incident of it.
    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()
    await kind.judge.click()
    await expect(kind.judgementClass).toHaveText('AI: Probe, 92% sure')

    await threats.goto('suspect')
    await expect(threats.count('suspect')).toHaveText('0')
    await expect(threats.count('background')).toHaveText('1')
    await expect(threats.laneEmpty).toContainText('No suspects')
    await dashboard.goto()
    await expect(dashboard.filteredCleared).toContainText('1 set aside by the AI as background')
    await dashboard.filteredCleared.click()
    await expect(threats.lane('background')).toHaveClass(/v-btn--active/)
  })

  test('take the kind back from the AI when you say it must never be set aside', async ({
    harness,
    aiSettings,
    threats,
    kinds,
    kind,
  }) => {
    await harness.createIncidents([MAYBE])
    await turnOnAi(harness, aiSettings)
    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()
    await kind.judge.click()
    await expect(kind.judgementClass).toHaveText('AI: Probe, 92% sure')
    await threats.goto('suspect')
    await expect(threats.count('suspect')).toHaveText('0')

    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()
    await kind.watch.click()
    await expect(kind.judgementOwner).toContainText('You watch it')

    await threats.goto('suspect')
    await expect(threats.count('suspect')).toHaveText('1')
    await expect(threats.cards.first()).toContainText(MAYBE_ADDRESS)
  })

  test('are told apart on the dashboard, which says how many reports the alerts came from', async ({
    harness,
    dashboard,
  }) => {
    await harness.createIncidents([
      {
        address: BOT,
        severity: 'low',
        programs: ['opnsense'],
        twin: 'ntopng',
        signals: 4,
        scan: true,
        minutes_ago: 10,
      },
    ])

    await dashboard.goto()

    await expect(dashboard.alertsTile.getByTestId('stat-hint')).toContainText('from 8 reports')
  })
})
