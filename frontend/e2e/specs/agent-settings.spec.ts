import { expect, test, turnOnAi } from '../support'

const KEY = 'sk-a-key-for-the-stand-in'

test.describe('Settings > Agents', () => {
  test('is a page of the settings, and the agents ask what Settings > AI chose until told otherwise', async ({
    page,
    settings,
    agentSettings,
  }) => {
    await settings.goto()

    await settings.agentsLink.click()

    await expect(page).toHaveURL('/settings/agents')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.agentsLink).toHaveAttribute('aria-current', 'page')
    await expect(agentSettings.headings).toHaveText([
      'Which AI the agents use',
      'What the agents may spend',
      'Tidying up',
    ])
    await expect(agentSettings.source('shared')).toBeChecked()
    await expect(agentSettings.state).toHaveText('Not asking an AI')
    await expect(agentSettings.reason).toContainText('AI is turned off.')
  })

  test('says who the agents ask once Settings > AI has a provider on', async ({
    harness,
    aiSettings,
    agentSettings,
  }) => {
    await turnOnAi(harness, aiSettings)

    await agentSettings.goto()

    await expect(agentSettings.state).toHaveText('Anthropic, claude-haiku-5-5')
    await expect(agentSettings.reason).toHaveCount(0)
  })

  test('keeps that the agents ask none, even while AI is on for everything else', async ({
    harness,
    aiSettings,
    agentSettings,
    agents,
    page,
  }) => {
    await turnOnAi(harness, aiSettings)
    await agentSettings.goto()

    await agentSettings.source('off').check()
    await agentSettings.save.click()

    await expect(agentSettings.saved).toHaveText('Saved.')
    await expect(agentSettings.state).toHaveText('Not asking an AI')
    await expect(agentSettings.reason).toContainText('AI is turned off for the agents.')
    await page.reload()
    await expect(agentSettings.source('off')).toBeChecked()
    await agents.goto()
    await expect(agents.ai).toContainText('AI is turned off for the agents.')
  })

  test('gives the agents a provider and a model of their own, set up right there', async ({
    harness,
    aiSettings,
    agentSettings,
    agents,
    page,
  }) => {
    await harness.standIn({
      kind: 'anthropic',
      api_key: KEY,
      models: ['claude-haiku-5-5', 'claude-sonnet-5-5'],
      provider: 'anthropic',
    })
    await agentSettings.goto()
    await agentSettings.source('own').check()

    await agentSettings.provider('anthropic').click()
    await expect(agentSettings.notReady).toContainText('Save the provider first')
    await aiSettings.apiKey('anthropic').fill(KEY)
    await aiSettings.test('anthropic').click()
    await expect(aiSettings.status('anthropic')).toHaveText('Connected')
    await expect(agentSettings.notReady).toHaveCount(0)
    await agentSettings.openModels()
    await page.getByRole('option', { name: /Sonnet 5\.5/ }).click()
    await agentSettings.save.click()

    await expect(agentSettings.saved).toHaveText('Saved.')
    await expect(agentSettings.state).toHaveText('Anthropic, claude-sonnet-5-5')
    // AI is still off under Settings > AI: this is theirs alone.
    await agents.goto()
    await expect(agents.ai).toHaveCount(0)
  })

  test('keeps limits on what the agents may spend, and says what is wrong with an amount', async ({
    agentSettings,
    page,
  }) => {
    await agentSettings.goto()

    await agentSettings.daily.fill('lots')
    await expect(agentSettings.saveLimits).toBeDisabled()
    await expect(page.getByTestId('agent-limit-daily-field')).toContainText('Use dollars and cents')
    await agentSettings.daily.fill('1.50')
    await agentSettings.monthly.fill('20')
    await agentSettings.saveLimits.click()

    await expect(agentSettings.limitsSaved).toBeVisible()
    await expect(page.getByTestId('agent-limit-day')).toContainText('$0.00 of $1.50')
    await expect(page.getByTestId('agent-limit-month')).toContainText('$0.00 of $20.00')
    await page.reload()
    await expect(agentSettings.daily).toHaveValue('1.5')
    await expect(agentSettings.monthly).toHaveValue('20')
  })

  test('lets the noise cleaner act on the surest of what it finds, if told to', async ({
    agentSettings,
    page,
  }) => {
    await agentSettings.goto()
    await expect(agentSettings.cleanup('suggest')).toBeChecked()

    await agentSettings.cleanup('auto').check()
    await agentSettings.saveCleanup.click()

    await expect(agentSettings.cleanupSaved).toBeVisible()
    await page.reload()
    await expect(agentSettings.cleanup('auto')).toBeChecked()
  })
})
