import { expect, test } from '../support'

/** A few days of reading incidents with Claude Haiku, and one chat on a model with no price. */
const CALLS = [
  { about: 'incident 3', hours_ago: 2, cost_micros: 2_500, repeat: 3 },
  { about: 'incident 4', hours_ago: 30, cost_micros: 4_000, cached_tokens: 600 },
  { purpose: 'chat', provider: 'ollama', model: 'llama3', cost_micros: 0, hours_ago: 6 },
  { purpose: 'chat', model: 'a-model-nobody-priced', cost_micros: null, hours_ago: 7 },
  { about: 'incident 5', ok: false, error: "It didn't answer in time.", hours_ago: 50 },
]

test.describe('AI usage', () => {
  test('is a place in the menu that says AI has not been asked, before it has', async ({
    page,
    dashboard,
    shell,
    aiUsage,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await shell.goTo('ai-usage')

    await expect(page).toHaveURL('/ai-usage')
    await expect(page).toHaveTitle('AI usage · AresGate')
    await shell.expectCurrent('ai-usage')
    await expect(page.getByTestId('page-heading')).toHaveText('AI usage')
    await expect(aiUsage.never).toContainText("AI hasn't been asked anything yet")
    await aiUsage.never.getByRole('link', { name: 'Set up an AI provider' }).click()
    await expect(page).toHaveURL('/settings/ai')
  })

  test('is no longer a page of Settings, and the old address leads here', async ({
    page,
    settings,
    aiUsage,
  }) => {
    await settings.goto()
    await expect(settings.nav).toBeVisible()
    await expect(settings.nav.getByRole('link', { name: 'AI usage' })).toHaveCount(0)
    await expect(settings.aiLink).toBeVisible()

    await page.goto('/settings/ai-usage?x=1')

    await expect(page).toHaveURL('/ai-usage?x=1')
    await expect(page.getByTestId('page-heading')).toHaveText('AI usage')
    await expect(aiUsage.never).toBeVisible()
  })

  test('is found in the command palette by what it is for', async ({ page, dashboard, shell }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    await shell.openPaletteWithKeys()

    await shell.paletteSearch.fill('spending')
    await expect(shell.paletteRows).toHaveText(['AI usage'])
    await shell.chooseCommand('spending')

    await expect(page).toHaveURL('/ai-usage')
    await expect(shell.palette).toBeHidden()
  })

  test('adds up what was asked, what it took and what it cost', async ({ harness, aiUsage }) => {
    await harness.createAiCalls(CALLS)

    await aiUsage.goto()

    await expect(aiUsage.costTile).toContainText('$0.01')
    await expect(aiUsage.tokensTile).toContainText('10.5K')
    await expect(aiUsage.requestsTile).toContainText('1 failed')
    // Where the month is heading is only worked out once a day of it has passed, so which words
    // it uses depends on the day this runs; the page's own tests have each.
    await expect(aiUsage.monthTile).toContainText(
      /Too early in the month to say where it is heading|On course for about \$/,
    )
    // Every request is listed, newest first.
    await expect(aiUsage.requests).toHaveCount(7)
    await expect(aiUsage.requests.first()).toContainText('Reading incidents, incident 3')
    await expect(aiUsage.requests.last()).toContainText('incident 5')
    await expect(aiUsage.requests.last()).toContainText("Failed: It didn't answer in time.")
  })

  test('says the costs are estimates, from the pages the prices were read on, and which have no price', async ({
    harness,
    aiUsage,
  }) => {
    await harness.createAiCalls(CALLS)

    await aiUsage.goto()

    await expect(aiUsage.estimate).toContainText('Costs are estimates')
    await expect(aiUsage.estimate.getByRole('link', { name: 'Anthropic' })).toHaveAttribute(
      'href',
      'https://platform.claude.com/docs/en/about-claude/pricing',
    )
    await expect(aiUsage.estimate).toContainText('1 request used a model with no known price')
  })

  test('charts the days, and the models, in cost, tokens or calls', async ({
    harness,
    aiUsage,
  }) => {
    await harness.createAiCalls(CALLS)

    await aiUsage.goto()
    await expect(aiUsage.dailyChart).toBeVisible()
    await expect(aiUsage.groupsChart).toContainText('Claude Haiku 5.5')

    await aiUsage.metric('tokens').click()
    await expect(aiUsage.dailyChart).toContainText('Tokens by day')
    await aiUsage.metric('calls').click()
    await expect(aiUsage.dailyChart).toContainText('Calls by day')

    await aiUsage.grouping('provider').click()
    await expect(aiUsage.groupsChart).toContainText('Anthropic')
    await aiUsage.grouping('use').click()
    await expect(aiUsage.groupsChart).toContainText('Chat')
  })

  test('lists what took the most, with a link to the incident', async ({
    page,
    harness,
    aiUsage,
  }) => {
    await harness.createAiCalls(CALLS)
    await aiUsage.goto()

    // Incident 3 was asked about three times, so it cost more than incident 4.
    await expect(aiUsage.topItems.first()).toContainText('Reading incidents: incident 3')
    await expect(aiUsage.topItems.first()).toContainText('3 requests')

    await aiUsage.topItems.first().getByRole('link').click()
    await expect(page).toHaveURL(/\/incidents\/3$/)
  })

  test('shows another range', async ({ harness, aiUsage }) => {
    await harness.createAiCalls([...CALLS, { about: 'incident 9', hours_ago: 24 * 20 }])
    await aiUsage.goto()
    await expect(aiUsage.requests).toHaveCount(8)

    await aiUsage.range('7d').click()

    await expect(aiUsage.requests).toHaveCount(7)
    await expect(aiUsage.costTile).toContainText('In the last 7 days')
  })

  test('opens a request to show exactly what the provider was sent', async ({
    harness,
    aiUsage,
  }) => {
    await harness.createAiCalls([{ about: 'incident 3' }])
    await aiUsage.goto()

    await aiUsage.requests
      .first()
      .getByRole('button', { name: /See what was sent/ })
      .click()

    await expect(aiUsage.dialog).toContainText('HOST_1 was scanned by WAN_1 on port 22.')
    await expect(aiUsage.dialog).toContainText('HOST_1 was probed by WAN_1; nothing got in.')
    await expect(aiUsage.dialog).toContainText('stand-ins')
    await aiUsage.dialog.getByRole('button', { name: 'Close' }).click()
    await expect(aiUsage.dialog).toHaveCount(0)
  })

  test('shows the rest of the requests a page at a time', async ({ harness, aiUsage }) => {
    await harness.createAiCalls([{ repeat: 30 }])
    await aiUsage.goto()
    await expect(aiUsage.requests).toHaveCount(25)

    await aiUsage.more.click()

    await expect(aiUsage.requests).toHaveCount(30)
    await expect(aiUsage.more).toHaveCount(0)
  })

  test('lets the owner choose how much AI is used without being asked, before it was ever asked', async ({
    page,
    aiUsage,
  }) => {
    await aiUsage.goto()
    await expect(aiUsage.never).toBeVisible()
    await expect(aiUsage.levelName).toHaveText('Medium')
    await expect(aiUsage.levelSummary).toContainText('rated medium or higher, up to 20 an hour')
    await expect(aiUsage.levelSave).toBeDisabled()

    await aiUsage.levelSlider.focus()
    await page.keyboard.press('ArrowRight')
    await expect(aiUsage.levelName).toHaveText('High')
    await expect(aiUsage.levelSummary).toContainText('rated low or higher, up to 60 an hour')
    await page.keyboard.press('Home')
    await expect(aiUsage.levelName).toHaveText('Very low')
    await expect(aiUsage.levelSummary).toContainText('Reads nothing by itself')
    await aiUsage.levelSave.click()

    await expect(aiUsage.levelSaved).toBeVisible()
    await expect(aiUsage.levelSave).toBeDisabled()
    // The level is kept, not just shown.
    await page.reload()
    await expect(aiUsage.levelName).toHaveText('Very low')
    await expect(aiUsage.levelSlider).toHaveAttribute('aria-valuetext', 'Very low')
  })

  test('keeps the spending limits, and shows how much of them has gone', async ({
    page,
    harness,
    aiUsage,
  }) => {
    await harness.createAiCalls([{ cost_micros: 900_000, hours_ago: 1 }])
    await aiUsage.goto()
    await expect(aiUsage.limitWords('day')).toHaveText('$0.90 spent, with no limit')

    await aiUsage.dailyField.fill('1')
    await aiUsage.monthlyField.fill('20.50')
    await aiUsage.saveLimits.click()

    await expect(aiUsage.limitsSaved).toBeVisible()
    await expect(aiUsage.limitWords('day')).toHaveText('$0.90 of $1.00: nearly used up')
    await expect(aiUsage.limitWords('month')).toContainText('of $20.50')
    // The limits are kept, not just shown.
    await page.reload()
    await expect(aiUsage.dailyField).toHaveValue('1')
    await expect(aiUsage.monthlyField).toHaveValue('20.5')
  })

  test('refuses an amount that makes no sense', async ({ page, harness, aiUsage }) => {
    await harness.createAiCalls([{}])
    await aiUsage.goto()

    await aiUsage.dailyField.fill('lots')

    await expect(page.getByText('Use dollars and cents')).toBeVisible()
    await expect(aiUsage.saveLimits).toBeDisabled()
  })

  test('downloads the requests as a spreadsheet', async ({ page, harness, aiUsage }) => {
    await harness.createAiCalls([{ about: 'incident 3' }, { about: 'incident 4' }])
    await aiUsage.goto()

    const [download] = await Promise.all([page.waitForEvent('download'), aiUsage.download.click()])

    expect(download.suggestedFilename()).toMatch(/^aresgate-ai-usage-\d{4}-\d{2}-\d{2}-30d\.csv$/)
  })
})
