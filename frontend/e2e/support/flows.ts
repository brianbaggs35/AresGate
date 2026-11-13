import { expect } from '@playwright/test'

import type { Harness } from './harness'
import type { AiSettingsPage } from './pages/ai-settings-page'
import type { IntegrationPage } from './pages/integration-page'

/** The key and secret that the OPNsense stand-in accepts. */
export const FIREWALL_KEY = 'a-valid-key'
export const FIREWALL_SECRET = 'a-valid-secret'

/**
 * Starts an OPNsense stand-in with these services installed, and connects to it through the
 * integration's page, pinning its certificate as a person would.
 */
export async function connectFirewall(
  harness: Harness,
  integration: IntegrationPage,
  services: string[],
  stopped: string[] = [],
): Promise<void> {
  const firewall = await harness.standIn({
    kind: 'opnsense',
    api_key: FIREWALL_KEY,
    api_secret: FIREWALL_SECRET,
    services,
    stopped,
  })
  await integration.goto('opnsense')
  await integration.address('api').fill(firewall.url)
  await integration.field('api', 'api_key').fill(FIREWALL_KEY)
  await integration.field('api', 'api_secret').fill(FIREWALL_SECRET)
  await integration.tlsMode('api', 'pinned').check()
  await integration.lookUp('api').click()
  await integration.trust('api').click()
  await integration.save.click()
  await expect(integration.status).toHaveText('Connected')
}

/** The key the Anthropic stand-in accepts. */
export const AI_KEY = 'sk-a-key-for-the-stand-in'

/**
 * Sets up Anthropic against a stand-in that answers like it, through the page for AI, and turns AI
 * on, as a person would: pick it, type the key, test it, and use it. What the AI decides counts
 * at once, as if the owner had told it to decide on its own.
 */
export async function turnOnAi(harness: Harness, aiSettings: AiSettingsPage): Promise<void> {
  // What the AI decides counts at once: the specs that use it are about what it does, and the
  // Review specs choose how much waits for the owner for themselves.
  await harness.setReview({ mode: 'auto' })
  await harness.standIn({
    kind: 'anthropic',
    api_key: AI_KEY,
    models: ['claude-haiku-5-5'],
    provider: 'anthropic',
  })
  await aiSettings.goto()
  await aiSettings.choose('anthropic')
  await aiSettings.apiKey('anthropic').fill(AI_KEY)
  await aiSettings.test('anthropic').click()
  await expect(aiSettings.status('anthropic')).toHaveText('Connected')
  await aiSettings.enabled.check()
  await expect(aiSettings.state).toHaveText('On · Claude Haiku 5.5')
}
