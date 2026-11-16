import type { DecisionRequest, IncidentRequest, VerdictRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

// This spec runs on a computer and on a phone, since it has no suffix.
const SCANNER = '8.8.4.10'
const OTHER = '8.8.5.11'

/** A scan the AI read as nothing, and would clear if it were let to. */
const SCAN = (address: string): IncidentRequest => ({
  address,
  severity: 'medium',
  signals: 2,
  minutes_ago: 20,
})
const NOTHING = (address: string, confidence = 92): DecisionRequest => ({
  address,
  subject: 'incident',
  ai_class: 'noise',
  confidence,
  verdict: 'not_suspicious',
  headline: 'The scanner of a research project.',
})
/** A verdict the AI gave by itself about an incident it read. */
const CLEARED = (address: string): VerdictRequest => ({
  verdict: 'not_suspicious',
  address,
  by_ai: true,
  incident: address,
})

test.describe('Cleared by the AI', () => {
  test('is a place of its own, and has nothing to look at on a new install', async ({
    page,
    cleared,
  }) => {
    await cleared.goto()

    await expect(page).toHaveTitle('Cleared by the AI · AresGate')
    await expect(cleared.heading).toHaveText('Cleared by the AI')
    await expect(cleared.empty).toContainText('Nothing is waiting')
    await expect(cleared.list('waiting')).toHaveText('Waiting for you 0')
    await expect(cleared.list('cleared')).toHaveText('Cleared by the AI 0')
    await expect(cleared.settingsLink).toHaveAttribute('href', '/settings/ai')
  })

  test('lists what the AI suggests clearing, with why, and clears one when confirmed', async ({
    harness,
    cleared,
  }) => {
    await harness.createIncidents([SCAN(SCANNER), SCAN(OTHER)])
    await harness.createDecisions([NOTHING(SCANNER), NOTHING(OTHER)])

    await cleared.goto()

    await expect(cleared.cards).toHaveCount(2)
    await expect(cleared.list('waiting')).toHaveText('Waiting for you 2')
    const card = cleared.card(SCANNER)
    await expect(card.getByTestId('cleared-state')).toHaveText('Waiting for you')
    await expect(card.getByTestId('cleared-verdict')).toHaveText('Not suspicious')
    await expect(card.getByTestId('cleared-confidence')).toHaveText('92% sure')
    await expect(card.getByTestId('cleared-reason')).toContainText(
      'The scanner of a research project.',
    )

    await cleared.confirm(card).click()

    await expect(cleared.notice).toHaveText('You confirmed 1 incident.')
    await expect(cleared.cards).toHaveCount(1)
    await expect(cleared.list('waiting')).toHaveText('Waiting for you 1')
  })

  test('says what the AI cleared by itself, confirms or takes it back, and the incident tells of it', async ({
    harness,
    cleared,
    page,
  }) => {
    await harness.createIncidents([SCAN(SCANNER), SCAN(OTHER)])
    await harness.createVerdicts([CLEARED(SCANNER), CLEARED(OTHER)])

    await cleared.goto()
    await cleared.list('cleared').click()

    await expect(cleared.cards).toHaveCount(2)
    await expect(cleared.card(SCANNER).getByTestId('cleared-state')).toHaveText('Cleared by the AI')
    await cleared.confirm(cleared.card(SCANNER)).click()
    await expect(cleared.notice).toHaveText('You confirmed 1 incident.')
    await expect(cleared.cards).toHaveCount(1)

    const incident = await cleared.card(OTHER).getByTestId('cleared-link').getAttribute('href')
    await cleared.takeBack(cleared.card(OTHER)).click()
    await expect(cleared.notice).toHaveText('You took back 1 incident.')
    await expect(cleared.empty).toContainText('Nothing to confirm')

    // The incident says what became of the AI clearing it.
    await page.goto(incident ?? '')
    await expect(cleared.trail).toContainText('took back what the AI cleared')
  })

  test('changes the verdict of many at once, after asking', async ({ harness, cleared }) => {
    await harness.createIncidents([SCAN(SCANNER), SCAN(OTHER)])
    await harness.createVerdicts([CLEARED(SCANNER), CLEARED(OTHER)])

    await cleared.goto()
    await cleared.list('cleared').click()
    await cleared.pickAll.check()
    await expect(cleared.confirmPicked).toHaveText('Confirm 2')
    await cleared.takeBackPicked.click()
    await cleared.accept.click()

    await expect(cleared.notice).toHaveText('You took back 2 incidents.')
    await expect(cleared.cards).toHaveCount(0)
  })

  test('shows on the dashboard that the AI cleared something', async ({
    harness,
    cleared,
    dashboard,
    shell,
    page,
  }) => {
    await harness.createIncidents([SCAN(SCANNER)])
    await harness.createVerdicts([CLEARED(SCANNER)])

    await dashboard.goto()
    await expect(cleared.nudge).toContainText('1 incident cleared by the AI that is not confirmed')
    await cleared.nudgeOpen.click()
    await shell.expectCurrent('cleared')
    await expect(page).toHaveURL(/state=cleared/)
    await expect(cleared.cards).toHaveCount(1)
  })

  test('has no WCAG 2.2 AA problems', async ({ page, harness, cleared }) => {
    await harness.createIncidents([SCAN(SCANNER), SCAN(OTHER)])
    await harness.createDecisions([NOTHING(SCANNER)])
    await harness.createVerdicts([CLEARED(OTHER)])
    await cleared.goto()
    await expect(cleared.cards).toHaveCount(1)

    await expectAccessible(page)
    await cleared.list('cleared').click()
    await expect(cleared.cards).toHaveCount(1)
    await expectAccessible(page)
  })
})
