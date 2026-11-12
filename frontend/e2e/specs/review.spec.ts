import type { DecisionRequest, IncidentRequest } from '../support'
import { expect, test } from '../support'

const SCANNER = '8.8.4.10'
const ATTACKER = '93.184.216.34'

/** A bot that swept the network, as the internet does all day. */
const SWEEP: IncidentRequest = {
  address: SCANNER,
  severity: 'low',
  programs: ['opnsense'],
  signals: 6,
  scan: true,
  neighbours: 2,
  waves: 2,
  ports: [22, 80, 443],
  minutes_ago: 30,
}

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

/** The AI set the sweeps' kind aside as a probe, and called the attack what it is. */
const SET_ASIDE: DecisionRequest = { address: SCANNER, ai_class: 'probe', confidence: 93 }
const ALARM: DecisionRequest = {
  address: ATTACKER,
  subject: 'incident',
  ai_class: 'compromise',
  confidence: 97,
  headline: 'A device answered the attacker after an exploit.',
}

test.describe('review', () => {
  test('is a place in the menu, and is all caught up on a new install', async ({
    page,
    shell,
    review,
  }) => {
    await review.goto()

    await expect(page).toHaveTitle('Review · AresGate')
    await expect(review.heading).toHaveText('Review')
    await expect(review.empty).toContainText('All caught up')
    await expect(review.badge).toHaveCount(0)
    await expect(review.cards).toHaveCount(0)
    await shell.expectCurrent('review')
  })

  test('lists what the AI decided and says what each would do, with a number on the menu', async ({
    harness,
    review,
    shell,
    dashboard,
  }) => {
    await harness.createIncidents([ATTACK, SWEEP])
    await harness.createDecisions([SET_ASIDE, ALARM])

    await review.goto()

    // What raises an alarm comes first, then what would set things aside.
    await expect(review.cards).toHaveCount(2)
    await expect(review.cards.first().getByTestId('review-kind')).toHaveText('Possible compromise')
    await expect(review.cards.first().getByTestId('review-confidence')).toHaveText('97% sure')
    await expect(review.cards.first().getByTestId('review-effect')).toContainText('counts')
    const sweep = review.cards.nth(1)
    await expect(sweep.getByTestId('review-kind')).toHaveText('Probe')
    await expect(sweep.getByTestId('review-effect')).toContainText('If you agree: Sets aside')
    await expect(sweep.getByTestId('review-state')).toHaveText('Waiting for you')
    await expect(review.list('waiting')).toHaveText('Waiting 2')
    // The alarm counts already, and it waits for the owner to agree like the rest.
    await expect(review.badge).toContainText('2')

    await dashboard.goto()
    await expect(review.nudge).toContainText('The AI has decided 2 things that wait for you')
    await review.nudgeOpen.click()
    await shell.expectCurrent('review')
  })

  test('takes an agreement, and moves the decision to what was answered', async ({
    harness,
    review,
  }) => {
    await harness.createIncidents([SWEEP])
    await harness.createDecisions([SET_ASIDE])
    await review.goto()

    await review.agree(review.cards.first()).click()

    await expect(review.empty).toBeVisible()
    await expect(review.badge).toHaveCount(0)
    await review.list('answered').click()
    await expect(review.cards).toHaveCount(1)
    await expect(review.said(review.cards.first())).toHaveText('You agreed.')
    await expect(review.cards.first().getByTestId('review-effect')).toContainText('It counts:')
    await expect(review.standing).toContainText('You agreed with 1 of 1 decisions (100%).')
  })

  test('takes a disagreement with a reason, and takes it back', async ({ harness, review }) => {
    await harness.createIncidents([SWEEP])
    await harness.createDecisions([SET_ASIDE])
    await review.goto()
    const card = review.cards.first()

    await review.addReason(card).click()
    await review.reason(card).fill('That is my own port scan from the laptop')
    await review.disagree(card).click()

    await expect(review.empty).toBeVisible()
    await review.list('answered').click()
    await expect(review.said(review.cards.first())).toContainText(
      'You disagreed. “That is my own port scan from the laptop”',
    )

    await review.undo(review.cards.first()).click()

    await expect(review.empty).toBeVisible()
    await review.list('waiting').click()
    await expect(review.cards).toHaveCount(1)
    await expect(review.badge).toContainText('1')
  })

  test('keeps a kind that was set aside so, when asked to', async ({ harness, review, page }) => {
    await harness.createIncidents([SWEEP])
    await harness.createDecisions([SET_ASIDE])
    await review.goto()
    const card = review.cards.first()

    await review.keep(card).check()
    await review.agree(card).click()
    await expect(review.empty).toBeVisible()

    await page.getByTestId('review-list-answered').click()
    await review.cards.first().getByTestId('review-link').click()
    await expect(page.getByTestId('judgement-owner')).toContainText('You set it aside.')
    await expect(page.getByTestId('strip-state')).toContainText('You agreed.')
  })

  test('agrees with everything shown, after asking', async ({ harness, review }) => {
    await harness.createIncidents([SWEEP, ATTACK])
    await harness.createDecisions([
      SET_ASIDE,
      { address: ATTACKER, subject: 'incident', ai_class: 'noise', confidence: 88 },
    ])
    await review.goto()
    await expect(review.cards).toHaveCount(2)

    await review.agreeAll.click()
    await review.confirm.click()

    await expect(review.notice).toHaveText('You agreed with 2 decisions.')
    await expect(review.empty).toBeVisible()
    await expect(review.list('answered')).toHaveText('Answered 2')
  })

  test('lists what was decided for you on its own', async ({ harness, review }) => {
    await harness.createIncidents([SWEEP])
    await harness.createDecisions([{ ...SET_ASIDE, review: 'auto' }])
    await review.goto()

    await expect(review.empty).toBeVisible()
    await review.list('decided').click()

    await expect(review.cards).toHaveCount(1)
    await expect(review.cards.first().getByTestId('review-state')).toHaveText('Decided for you')
    await expect(review.cards.first().getByTestId('review-effect')).toContainText('It counts:')
    await review.disagree(review.cards.first()).click()
    await expect(review.empty).toBeVisible()
  })

  test('shows the review on the kind and on the incident the AI judged', async ({
    harness,
    review,
    kind,
    incident,
    incidents,
    page,
  }) => {
    await harness.createIncidents([ATTACK, SWEEP])
    await harness.createDecisions([SET_ASIDE, { ...ALARM, review: 'pending' }])
    await review.goto()

    await review.cards.nth(1).getByTestId('review-link').click()
    await expect(kind.heading).toContainText('ET SCAN Potential SSH Scan')
    await expect(page.getByTestId('strip-state')).toContainText('Waiting for you.')
    await review.agree(page.getByTestId('review-strip')).click()
    await expect(page.getByTestId('strip-state')).toContainText('You agreed.')

    await incidents.goto()
    await incidents.cards.filter({ hasText: ATTACKER }).first().click()
    await expect(incident.heading).toBeVisible()
    await expect(page.getByTestId('strip-state')).toContainText('Waiting for you.')
  })

  test('has its own place in Settings, where how much waits is chosen and kept', async ({
    reviewSettings,
    page,
    review,
    harness,
  }) => {
    await harness.createIncidents([SWEEP])
    await harness.createDecisions([{ ...SET_ASIDE, review: 'auto' }])
    await reviewSettings.goto()

    await expect(reviewSettings.choice('all')).toBeChecked()
    await expect(reviewSettings.save).toBeDisabled()
    await expect(reviewSettings.fromBar).toHaveCount(0)

    await reviewSettings.choice('uncertain').check()
    await expect(reviewSettings.fromValue).toHaveText('85% sure')
    await reviewSettings.learn.uncheck()
    await reviewSettings.save.click()
    await expect(reviewSettings.saved).toHaveText('Saved.')

    await page.reload()
    await expect(reviewSettings.choice('uncertain')).toBeChecked()
    await expect(reviewSettings.learn).not.toBeChecked()

    await reviewSettings.choice('all').check()
    await reviewSettings.discard.click()
    await expect(reviewSettings.choice('uncertain')).toBeChecked()

    await review.goto()
    await expect(review.settingsLink).toBeVisible()
    await review.settingsLink.click()
    await expect(page).toHaveURL('/settings/review')
  })

  test('offers to let the AI decide alone once it has earned trust', async ({
    harness,
    review,
    page,
  }) => {
    const addresses = Array.from({ length: 22 }, (_, index) => `8.8.${(index + 10).toString()}.9`)
    await harness.createIncidents(
      addresses.map((address) => ({
        address,
        severity: 'low' as const,
        programs: ['opnsense'],
        signals: 2,
        minutes_ago: 30,
      })),
    )
    // Each address is in a network of its own, or they would be one incident, and the decisions
    // are about single incidents, so that they do not share a kind.
    await harness.createDecisions(
      addresses.map((address) => ({
        address,
        subject: 'incident' as const,
        ai_class: 'noise' as const,
        confidence: 90,
        review: 'agreed' as const,
      })),
    )
    await review.goto()

    await expect(review.standing).toContainText('22 of 22 decisions (100%)')
    await expect(review.offer).toBeVisible()
    await review.offer.click()
    await expect(page).toHaveURL('/settings/review')
  })
})
