import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

test.describe('verdicts page', () => {
  test('is one of the settings pages, and says none have been given on a new install', async ({
    page,
    settings,
    verdicts,
  }) => {
    await settings.goto()

    await settings.verdictsLink.click()

    await expect(page).toHaveURL('/settings/verdicts')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.verdictsLink).toHaveAttribute('aria-current', 'page')
    await expect(verdicts.card.getByTestId('section-title')).toHaveText('Verdicts')
    await expect(verdicts.empty).toContainText("You haven't given a verdict yet")
    await verdicts.empty.getByTestId('see-incidents').click()
    await expect(page).toHaveURL('/incidents')
  })

  test('lists each verdict with what it is about, why, and how often it was applied', async ({
    harness,
    verdicts,
  }) => {
    await harness.createIncidents([{ address: ATTACKER, signals: 3 }])
    await harness.createVerdicts([
      { verdict: 'not_suspicious', address: ATTACKER, note: 'my scanner' },
      { verdict: 'low_priority', signature: 'ET SCAN Potential SSH Scan', source: 'wazuh' },
    ])

    await verdicts.goto()

    await expect(verdicts.rows).toHaveCount(2)
    await expect(verdicts.says()).toHaveText(['Low priority', 'Not suspicious'])
    await expect(verdicts.about()).toHaveText([
      '“ET SCAN Potential SSH Scan” from any address, as seen by Wazuh',
      ATTACKER,
    ])
    await expect(verdicts.rows.nth(1).getByTestId('verdict-why')).toHaveText('Why: my scanner')
    // The verdict on the signature names more, so it decides for the two alerts it fits, and
    // the one on the address is left with the first.
    await expect(verdicts.rows.first().getByTestId('verdict-meta')).toContainText(
      'Applied to 2 signals',
    )
    await expect(verdicts.rows.nth(1).getByTestId('verdict-meta')).toContainText(
      'Applied to 1 signal,',
    )
  })

  test('changes what a verdict says and why, and keeps it', async ({ harness, page, verdicts }) => {
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
    await verdicts.goto()

    await verdicts.rows.first().getByTestId('verdict-change').click()
    await expect(verdicts.dialog).toContainText(ATTACKER)
    await expect(verdicts.say('not_suspicious')).toBeChecked()
    await verdicts.say('low_priority').check()
    await verdicts.note.fill('only noisy')
    await verdicts.save.click()

    await expect(verdicts.notice).toHaveText(`Changed: ${ATTACKER}.`)
    await expect(verdicts.says()).toHaveText(['Low priority'])
    await expect(verdicts.rows.first().getByTestId('verdict-why')).toHaveText('Why: only noisy')

    await page.reload()
    await expect(verdicts.says()).toHaveText(['Low priority'])
    await expect(verdicts.rows.first().getByTestId('verdict-why')).toHaveText('Why: only noisy')
  })

  test('closes the dialog without changing anything when it is cancelled', async ({
    harness,
    verdicts,
  }) => {
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
    await verdicts.goto()

    await verdicts.rows.first().getByTestId('verdict-change').click()
    await verdicts.say('threat').check()
    await verdicts.cancel.click()

    await expect(verdicts.dialog).toBeHidden()
    await expect(verdicts.says()).toHaveText(['Not suspicious'])
  })

  test('says why a change was not saved, and keeps the verdict as it was', async ({
    harness,
    page,
    verdicts,
  }) => {
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
    await verdicts.goto()
    await page.route('**/api/verdicts/*', (route) =>
      route.request().method() === 'PATCH' ? route.abort() : route.continue(),
    )

    await verdicts.rows.first().getByTestId('verdict-change').click()
    await verdicts.say('threat').check()
    await verdicts.save.click()

    await expect(verdicts.failure).toBeVisible()
    await expect(verdicts.says()).toHaveText(['Not suspicious'])
  })

  test('takes a verdict back once it is confirmed, and the incident is judged again', async ({
    harness,
    incidents,
    page,
    verdicts,
  }) => {
    await harness.createIncidents([{ address: ATTACKER, signals: 3 }])
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(0)
    await verdicts.goto()

    await verdicts.rows.first().getByTestId('verdict-remove').click()
    await expect(verdicts.confirmTitle).toHaveText('Take this verdict back?')
    await expect(page.getByTestId('confirm-message')).toContainText(
      '3 signals it was applied to are judged again',
    )
    await verdicts.confirm.click()

    await expect(verdicts.notice).toHaveText(`Taken back: ${ATTACKER}.`)
    await expect(verdicts.empty).toBeVisible()
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)
  })

  test('keeps a verdict when taking it back is not confirmed', async ({
    harness,
    page,
    verdicts,
  }) => {
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
    await verdicts.goto()

    await verdicts.rows.first().getByTestId('verdict-remove').click()
    await page.getByTestId('confirm-cancel').click()

    await expect(verdicts.rows).toHaveCount(1)
    await expect(verdicts.notice).toBeHidden()
  })

  test('says so when the verdicts cannot be loaded, and loads them once they can', async ({
    harness,
    page,
    verdicts,
  }) => {
    await harness.createVerdicts([{ verdict: 'threat', address: ATTACKER }])
    await page.route('**/api/verdicts', (route) => route.abort())

    await verdicts.goto()

    await expect(verdicts.error).toBeVisible()
    await page.unroute('**/api/verdicts')
    await verdicts.error.getByRole('button').click()
    await expect(verdicts.rows).toHaveCount(1)
  })

  test('is in the activity, as a verdict someone gave', async ({ harness, activity, page }) => {
    await harness.createIncidents([{ address: ATTACKER }])
    await page.goto('/incidents')
    await page.getByTestId('incident').first().click()
    await page.getByTestId('give-low_priority').click()
    await expect(page.getByTestId('verdict-notice')).toBeVisible()

    await activity.goto()

    await expect(activity.entries.first()).toContainText('A verdict was given')
  })
})

test.describe('verdicts from the list of incidents', () => {
  test('quiets an incident with one press, says so, and takes it back', async ({
    harness,
    incidents,
    verdicts,
  }) => {
    await harness.createIncidents([{ address: ATTACKER, signals: 2 }])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)

    await incidents.quick('not_suspicious').click()

    await expect(incidents.judged).toHaveText(`Remembered: ${ATTACKER} is not suspicious.`)
    // Nothing is left that needs anyone, so the incident leaves the list.
    await expect(incidents.cards).toHaveCount(0)
    await expect(incidents.empty).toContainText('Every incident is one you called')
    await verdicts.goto()
    await expect(verdicts.about()).toHaveText([ATTACKER])

    await incidents.goto()
    await incidents.quieted.click()
    await incidents.quick('threat').click()
    await expect(incidents.judged).toHaveText(
      `Remembered: ${ATTACKER} is a real threat. It was not suspicious.`,
    )
    await incidents.undo.click()
    await expect(incidents.judged).toHaveText('Taken back.')
    await expect(incidents.quick('not_suspicious')).toBeVisible()
    await verdicts.goto()
    await expect(verdicts.says()).toHaveText(['Not suspicious'])
  })

  test('takes back a new verdict, and the incident comes back', async ({
    harness,
    incidents,
    verdicts,
  }) => {
    await harness.createIncidents([{ address: ATTACKER }])
    await incidents.goto()

    await incidents.quick('low_priority').click()
    await expect(incidents.cards).toHaveCount(0)
    await incidents.undo.click()

    await expect(incidents.judged).toHaveText('Taken back.')
    await expect(incidents.cards).toHaveCount(1)
    await verdicts.goto()
    await expect(verdicts.empty).toBeVisible()
  })

  test('marks an incident a real threat and keeps it in the list', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents([{ address: ATTACKER }])
    await incidents.goto()

    await incidents.quick('threat').click()

    await expect(incidents.judged).toHaveText(`Remembered: ${ATTACKER} is a real threat.`)
    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.cards.first().getByTestId('verdict')).toHaveText('Real threat')
  })

  test('says so when the verdict could not be given, and can be tried again', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents([{ address: ATTACKER }])
    await incidents.goto()
    await page.route('**/api/verdicts', (route) => route.abort())

    await incidents.quick('low_priority').click()

    await expect(page.getByTestId('quick-error')).toContainText("Can't reach AresGate")
    await page.unroute('**/api/verdicts')
    await incidents.quick('low_priority').click()
    await expect(incidents.judged).toBeVisible()
  })

  test('leaves the card a link to the incident, with the buttons beside it', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents([{ address: ATTACKER }])
    await incidents.goto()

    await expect(incidents.cards.first().getByTestId('quick-threat')).toHaveCount(0)
    await incidents.cards.first().click()

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })
})
