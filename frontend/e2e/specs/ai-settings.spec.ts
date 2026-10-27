import { expect, test } from '../support'

const KEY = 'sk-a-key-for-the-stand-in'
const HAIKU = 'claude-haiku-5-5'

test.describe('Settings > AI', () => {
  test('is a page of the settings, with a card for each provider and the prices it can be asked at', async ({
    page,
    settings,
    aiSettings,
  }) => {
    await settings.goto()

    await settings.aiLink.click()

    await expect(page).toHaveURL('/settings/ai')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.aiLink).toHaveAttribute('aria-current', 'page')
    await expect(aiSettings.cards).toHaveText([
      'Use AI',
      'Anthropic',
      'OpenAI',
      'Ollama (your computer)',
      'Ollama Cloud',
    ])
    // Anthropic starts on Haiku 5.5 and OpenAI on GPT-6 Luna, with what each costs.
    await expect(aiSettings.model('anthropic')).toContainText('Claude Haiku 5.5')
    await expect(aiSettings.price('anthropic')).toContainText(
      '$0.10 in, $0.50 out per million tokens',
    )
    await expect(aiSettings.price('anthropic')).toContainText('over 100,000 tokens')
    await expect(aiSettings.price('anthropic')).toContainText(
      'Caches the fixed start of each prompt for 5 minutes: $0.01 to read it back and $0.125 to write it',
    )
    await expect(aiSettings.model('openai')).toContainText('GPT-6 Luna')
    await expect(aiSettings.price('openai')).toContainText('$0.10 in, $0.50 out per million tokens')
    await expect(aiSettings.price('openai')).toContainText('for 30 minutes')
    await expect(aiSettings.price('anthropic').getByRole('link')).toHaveAttribute(
      'href',
      /^https:\/\/platform\.claude\.com\//,
    )
    // Nothing is set up, so AI cannot be turned on yet.
    await expect(aiSettings.enabled).toBeDisabled()
    await expect(aiSettings.useCard).toContainText('Set up a provider below first')
  })

  test('offers the other models of a provider, each with its price', async ({ aiSettings }) => {
    await aiSettings.goto()

    await aiSettings.chooseModel('anthropic', /Sonnet 5\.5/)

    await expect(aiSettings.price('anthropic')).toContainText(
      '$2.00 in, $10.00 out per million tokens',
    )
    await expect(aiSettings.price('anthropic')).not.toContainText('over 100,000 tokens')

    await aiSettings.chooseModel('openai', /GPT-6 Astra/)

    await expect(aiSettings.price('openai')).toContainText(
      '$10.00 in, $50.00 out per million tokens',
    )
    await expect(aiSettings.price('openai')).toContainText('over 272,000 tokens')
    await expect(aiSettings.price('openai')).not.toContainText('deprecated')
  })

  test('says that an older model is being retired and caches by itself', async ({ aiSettings }) => {
    await aiSettings.goto()

    await aiSettings.chooseModel('openai', /GPT-5\.4 nano/)

    await expect(aiSettings.price('openai')).toContainText(
      'OpenAI lists this model as deprecated, so it will be retired',
    )
    await expect(aiSettings.price('openai')).toContainText('by itself at no extra charge')
  })

  test('tests a provider with a key, keeps the key out of sight and turns AI on', async ({
    page,
    harness,
    aiSettings,
  }) => {
    await harness.standIn({
      kind: 'anthropic',
      api_key: KEY,
      models: [HAIKU],
      provider: 'anthropic',
    })
    await aiSettings.goto()
    await expect(aiSettings.test('anthropic')).toBeDisabled()

    await aiSettings.apiKey('anthropic').fill(KEY)
    await aiSettings.test('anthropic').click()

    await expect(aiSettings.notice('anthropic')).toContainText(
      'claude-haiku-5-5 answered. It counted 14 tokens in and 1 out.',
    )
    await expect(aiSettings.status('anthropic')).toHaveText('Connected')
    // The key was kept, and is not shown again.
    await expect(aiSettings.apiKey('anthropic')).toHaveValue('')
    await expect(aiSettings.apiKey('anthropic')).toHaveAttribute('placeholder', 'Saved')
    await expect(page.getByText(KEY)).toHaveCount(0)
    expect(await page.content()).not.toContain(KEY)

    await expect(aiSettings.enabled).toBeEnabled()
    await aiSettings.enabled.check()

    await expect(aiSettings.provider).toContainText('Anthropic')
    await page.reload()
    await expect(aiSettings.enabled).toBeChecked()
    await expect(aiSettings.provider).toContainText('Anthropic')
    await expect(aiSettings.status('anthropic')).toHaveText('Connected')
  })

  test('says why a key was not accepted', async ({ harness, aiSettings }) => {
    await harness.standIn({
      kind: 'openai',
      api_key: KEY,
      models: ['gpt-6-luna'],
      provider: 'openai',
    })
    await aiSettings.goto()

    await aiSettings.apiKey('openai').fill('the-wrong-key')
    await aiSettings.test('openai').click()

    await expect(aiSettings.lastError('openai')).toContainText("OpenAI didn't accept the API key")
    await expect(aiSettings.status('openai')).toHaveText('Problem')
    await expect(aiSettings.notice('openai')).toHaveCount(0)
  })

  test('fetches the models an Ollama has, tests it with one and keeps the choice', async ({
    page,
    harness,
    aiSettings,
  }) => {
    const ollama = await harness.standIn({ kind: 'ollama', models: ['qwen3:8b', 'llama3.2:3b'] })
    await aiSettings.goto()
    await expect(aiSettings.fetchModels('ollama')).toBeDisabled()

    await aiSettings.address('ollama').fill(ollama.url)
    await aiSettings.fetchModels('ollama').click()

    await expect(aiSettings.notice('ollama')).toHaveText('It has 2 models.')
    await expect(aiSettings.model('ollama')).toContainText('2 found models')
    await aiSettings.chooseModel('ollama', /qwen3:8b/)
    await aiSettings.test('ollama').click()

    await expect(aiSettings.notice('ollama')).toContainText(
      'Reached it (2 models), and qwen3:8b answered.',
    )
    await expect(aiSettings.status('ollama')).toHaveText('Connected')
    await expect(aiSettings.card('ollama').getByTestId('provider-free')).toBeVisible()

    await page.reload()
    await expect(aiSettings.modelInput('ollama')).toHaveValue('qwen3:8b')
    await expect(aiSettings.address('ollama')).toHaveValue(ollama.url)
  })

  test('only accepts an Ollama on the home network', async ({ page, aiSettings }) => {
    await aiSettings.goto()

    await aiSettings.address('ollama').fill('http://8.8.8.8:11434')
    await aiSettings.save('ollama').click()

    await expect(aiSettings.card('ollama').getByTestId('provider-url')).toContainText(
      "isn't a private network address",
    )
    await expect(aiSettings.address('ollama')).toBeFocused()
    await expect(aiSettings.status('ollama')).toHaveCount(0)
    expect(page.url()).toContain('/settings/ai')
  })

  test('fetches the models of Ollama’s cloud once there is a key', async ({
    harness,
    aiSettings,
  }) => {
    await harness.standIn({
      kind: 'ollama',
      api_key: KEY,
      models: ['gemma4:31b'],
      provider: 'ollama_cloud',
    })
    await aiSettings.goto()
    await expect(aiSettings.fetchModels('ollama_cloud')).toBeDisabled()

    await aiSettings.apiKey('ollama_cloud').fill(KEY)
    await expect(aiSettings.fetchModels('ollama_cloud')).toBeEnabled()
    await aiSettings.fetchModels('ollama_cloud').click()

    await expect(aiSettings.notice('ollama_cloud')).toHaveText('It has 1 model.')
    await aiSettings.chooseModel('ollama_cloud', /gemma4:31b/)
    await aiSettings.test('ollama_cloud').click()
    await expect(aiSettings.status('ollama_cloud')).toHaveText('Connected')
  })

  test('forgets a provider and its key, and turns AI off if it was the one asked', async ({
    harness,
    aiSettings,
  }) => {
    await harness.standIn({
      kind: 'anthropic',
      api_key: KEY,
      models: [HAIKU],
      provider: 'anthropic',
    })
    await aiSettings.goto()
    await aiSettings.apiKey('anthropic').fill(KEY)
    await aiSettings.test('anthropic').click()
    await aiSettings.enabled.check()
    await expect(aiSettings.enabled).toBeChecked()

    await aiSettings.remove('anthropic').click()
    await expect(aiSettings.confirmTitle).toHaveText('Remove Anthropic?')
    await aiSettings.confirm.click()

    await expect(aiSettings.status('anthropic')).toHaveCount(0)
    await expect(aiSettings.apiKey('anthropic')).not.toHaveAttribute('placeholder', 'Saved')
    await expect(aiSettings.enabled).not.toBeChecked()
    await expect(aiSettings.enabled).toBeDisabled()
    expect((await harness.rowCounts()).credentials).toBe(0)
  })

  test('says so when the page can’t be loaded, and loads it again on request', async ({
    page,
    aiSettings,
  }) => {
    let fail = true
    await page.route('**/api/ai', (route) => (fail ? route.abort() : route.continue()))
    await aiSettings.goto()

    await expect(aiSettings.error).toContainText("Can't reach AresGate.")

    fail = false
    await aiSettings.error.getByRole('button').click()

    await expect(aiSettings.error).toHaveCount(0)
    await expect(aiSettings.cards.first()).toBeVisible()
  })
})
