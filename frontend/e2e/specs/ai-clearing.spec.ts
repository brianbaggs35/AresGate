import { expect, expectAccessible, test } from '../support'

// This spec runs on a computer and on a phone, since it has no suffix.
test.describe('Settings > AI > Clearing', () => {
  test('starts as suggesting, balanced and up to medium, with the terms in words', async ({
    aiSettings,
  }) => {
    await aiSettings.goto()

    await expect(aiSettings.clearing).toBeVisible()
    await expect(aiSettings.mode('suggest')).toBeChecked()
    await expect(aiSettings.minimum).toHaveText('80% sure')
    await expect(aiSettings.presetWords).toContainText('quite sure')
    await expect(aiSettings.ceilingWords).toHaveText(
      'Up to medium. High and critical are left to you.',
    )
    for (const kind of ['noise', 'probe', 'unclear'] as const) {
      await expect(aiSettings.kind(kind)).toBeChecked()
    }
    // The cap is for an AI that clears by itself.
    await expect(aiSettings.cap).toHaveCount(0)
    await expect(aiSettings.clearingSave).toBeDisabled()
  })

  test('says how many incidents it would have cleared before anything is saved', async ({
    aiSettings,
    harness,
  }) => {
    // The preview counts the incidents the AI has read lately, so it has read one.
    await harness.createIncidents([{ address: '8.8.4.10', severity: 'medium', signals: 2 }])
    await harness.createDecisions([
      {
        address: '8.8.4.10',
        subject: 'incident',
        ai_class: 'noise',
        confidence: 92,
        headline: 'The scanner of a research project.',
      },
    ])
    await aiSettings.goto()

    await aiSettings.preset('careful').click()

    await expect(aiSettings.minimum).toHaveText('90% sure')
    await expect(aiSettings.clearingPreview).toContainText(
      /Of the 1 incident the AI read in the last 7 days, these settings would have cleared/,
    )
    await expect(aiSettings.clearingSave).toBeEnabled()
  })

  test('keeps what is chosen, and asks for the most it clears a day when it clears by itself', async ({
    aiSettings,
  }) => {
    await aiSettings.goto()

    await aiSettings.mode('automatic').check()
    await aiSettings.cap.fill('5')
    await aiSettings.preset('thorough').click()
    await aiSettings.kind('unclear').uncheck()
    await aiSettings.ceiling('high').click()
    await expect(aiSettings.ceilingWords).toHaveText('Up to high. Critical is always left to you.')
    await aiSettings.clearingSave.click()
    await expect(aiSettings.clearingSaved).toBeVisible()

    await aiSettings.goto()
    await expect(aiSettings.mode('automatic')).toBeChecked()
    await expect(aiSettings.minimum).toHaveText('65% sure')
    await expect(aiSettings.cap).toHaveValue('5')
    await expect(aiSettings.kind('unclear')).not.toBeChecked()
    await expect(aiSettings.kind('noise')).toBeChecked()
    await expect(aiSettings.clearingSave).toBeDisabled()
  })

  test('hides the terms when it is off, and puts the card back to what is kept', async ({
    aiSettings,
  }) => {
    await aiSettings.goto()

    await aiSettings.mode('off').check()
    await expect(aiSettings.preset('careful')).toHaveCount(0)
    await aiSettings.clearingDiscard.click()

    await expect(aiSettings.mode('suggest')).toBeChecked()
    await expect(aiSettings.preset('careful')).toBeVisible()
  })

  test('has nothing wider than the screen and no WCAG 2.2 AA problems', async ({
    page,
    aiSettings,
  }) => {
    await aiSettings.goto()
    await aiSettings.mode('automatic').check()
    await expect(aiSettings.cap).toBeVisible()
    await aiSettings.preset('careful').click()
    await expect(aiSettings.clearingPreview).toBeVisible()

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    await expectAccessible(page, { include: '[data-test="clearing-card"]' })
  })
})
