import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

const ATTACKER = '93.184.216.34'
const BOT = '8.8.4.10'

/** The one real attack, which is a kind of its own. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  severity: 'critical',
  programs: ['wazuh'],
  signals: 3,
  exploit: true,
  compromise: true,
  minutes_ago: 8,
}

/** Two bots that swept the network, in the same words from the same program: one kind. */
const SWEEPS: IncidentRequest[] = [
  {
    address: BOT,
    severity: 'low',
    programs: ['opnsense'],
    signals: 6,
    scan: true,
    neighbours: 2,
    waves: 2,
    ports: [22, 80, 443],
    minutes_ago: 30,
  },
  {
    address: '9.9.9.20',
    severity: 'low',
    programs: ['opnsense'],
    signals: 4,
    scan: true,
    ports: [22, 23],
    minutes_ago: 70,
  },
]

test.describe('the kinds of incident', () => {
  test('are listed from the threats page, and none are made on a new install', async ({
    page,
    threats,
    kinds,
  }) => {
    await threats.goto()

    await threats.kindsLink.click()

    await expect(page).toHaveURL('/threats/kinds')
    await expect(page).toHaveTitle('Threats · AresGate')
    await expect(kinds.heading).toHaveText('Kinds of incident')
    await expect(kinds.empty).toBeVisible()
    await expect(kinds.cards).toHaveCount(0)
  })

  test('group the incidents that are the same sort of thing, whoever sent them', async ({
    harness,
    kinds,
  }) => {
    await harness.createIncidents([ATTACK, ...SWEEPS])

    await kinds.goto()

    // The two bots' incidents are one kind; the attack is another.
    await expect(kinds.cards).toHaveCount(2)
    await expect(kinds.total).toContainText('2 kinds')
    const sweep = kinds.cards.filter({ hasText: 'ET SCAN Potential SSH Scan' })
    await expect(sweep).toHaveCount(1)
    await expect(sweep.getByTestId('family-incidents')).toContainText(
      '2 incidents from 2 addresses',
    )
    await expect(sweep.getByTestId('family-reach')).toContainText('From the internet')
    await expect(sweep.getByTestId('family-waiting')).toHaveText('Not judged yet')
  })

  test('are searched, and narrowed to a lane, as the address says', async ({
    harness,
    kinds,
    incidents,
    page,
  }) => {
    await harness.createIncidents([ATTACK, ...SWEEPS])
    await kinds.goto()

    await kinds.search.fill('scan')

    await expect(page).toHaveURL(/q=scan/)
    await expect(kinds.cards).toHaveCount(1)
    await kinds.search.fill('nothing like this')
    await expect(kinds.empty).toBeVisible()
    await kinds.search.fill('')
    await expect(kinds.cards).toHaveCount(2)

    await incidents.choose(kinds.lane, 'With threats')

    await expect(page).toHaveURL(/lane=threat/)
    await expect(kinds.cards).toHaveCount(1)
    await expect(kinds.cards.first().getByTestId('family-threats')).toContainText('1 threat')
  })

  test('open on a page of their own, which says why their incidents are where they are', async ({
    harness,
    kinds,
    kind,
    page,
  }) => {
    await harness.createIncidents([ATTACK, ...SWEEPS])
    await kinds.goto()

    await kinds.cards
      .filter({ hasText: 'ET SCAN Potential SSH Scan' })
      .getByTestId('family')
      .click()

    await expect(page).toHaveURL(/\/threats\/kinds\/\d+$/)
    await expect(kind.heading).toContainText('ET SCAN Potential SSH Scan')
    await expect(kind.judgementNone).toContainText('No AI has judged this kind yet')
    await expect(kind.why.first()).toBeVisible()
    await expect(kind.cards).toHaveCount(2)
    await kind.openInIncidents.click()
    await expect(page).toHaveURL(/\/incidents\?.*family=\d+/)
    await expect(page.getByTestId('incident-card')).toHaveCount(2)
  })

  test('say when they changed after the AI judged them, and that your word stands', async ({
    harness,
    kinds,
    kind,
  }) => {
    await harness.createIncidents(SWEEPS)
    await harness.createDecisions([
      { address: BOT, ai_class: 'probe', review: 'auto', changed: true },
    ])
    await kinds.goto()

    const sweep = kinds.cards.filter({ hasText: 'ET SCAN Potential SSH Scan' })
    await expect(sweep.getByTestId('family-changed')).toHaveText('Changed since judged')
    await sweep.getByTestId('family').click()

    await expect(kind.changed).toContainText('It has changed since it was judged')
    await expect(kind.changes.filter({ hasText: 'destination ports' })).toHaveCount(1)
    await expect(kind.changed).toContainText('The AI will be asked about it again')

    await kind.watch.click()

    await expect(kind.judgementOwner).toContainText('You watch it')
    await expect(kind.changed).toContainText('Your word on it stands')
  })

  test('are set aside by your word, whatever the AI says, until you take it back', async ({
    harness,
    kinds,
    kind,
    threats,
    page,
  }) => {
    await harness.createIncidents([ATTACK, ...SWEEPS])
    await kinds.goto()
    await kinds.cards
      .filter({ hasText: 'ET SCAN Potential SSH Scan' })
      .getByTestId('family')
      .click()

    await kind.background.click()

    await expect(kind.judgementOwner).toContainText('You set it aside')
    await expect(kind.background).toBeDisabled()
    await expect(kind.takeBack).toBeVisible()
    await threats.goto('background')
    await expect(threats.kinds.filter({ hasText: 'You set it aside' })).toHaveCount(1)

    await page.goBack()
    await kind.takeBack.click()

    await expect(kind.judgementOwner).toBeHidden()
    await expect(kind.judgementNone).toBeVisible()
  })

  test('are watched when you say no incident of them may be set aside', async ({
    harness,
    kinds,
    kind,
  }) => {
    await harness.createIncidents(SWEEPS)
    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()

    await kind.watch.click()

    await expect(kind.judgementOwner).toContainText('You watch it')
    await expect(kind.watch).toBeDisabled()
  })

  test('are judged by the AI once for all their incidents, when asked', async ({
    harness,
    aiSettings,
    kinds,
    kind,
    page,
  }) => {
    await harness.createIncidents(SWEEPS)
    await turnOnAi(harness, aiSettings)
    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()

    await kind.judge.click()

    await expect(kind.judgementClass).toHaveText('AI: Probe, 92% sure')
    await expect(kind.judgementReason).not.toBeEmpty()
    await expect(kind.judgementBy).toContainText('Judged by')
    await expect(kind.judge).toHaveText('Ask the AI again')
    await page.goto('/threats/kinds')
    await expect(kinds.cards.first().getByTestId('family-ai')).toHaveText('AI: Probe, 92% sure')
  })

  test('say plainly that the AI is off when it is asked', async ({ harness, kinds, kind }) => {
    await harness.createIncidents(SWEEPS)
    await kinds.goto()
    await kinds.cards.first().getByTestId('family').click()

    await kind.judge.click()

    await expect(kind.judgementFailure).toContainText('AI is turned off')
  })

  test('say so when one is gone', async ({ page, kind }) => {
    await page.goto('/threats/kinds/987654')

    await expect(kind.error).toContainText('may have been removed')
  })
})
