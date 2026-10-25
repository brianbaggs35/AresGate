import { expect } from '@playwright/test'

import type { Harness } from './harness'
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
): Promise<void> {
  const firewall = await harness.standIn({
    kind: 'opnsense',
    api_key: FIREWALL_KEY,
    api_secret: FIREWALL_SECRET,
    services,
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
