import type { Locator, Page } from '@playwright/test'

/** Settings > Agents: which AI the agents ask, with a provider and model of their own if they have
 * one, and what they may spend. */
export class AgentSettingsPage {
  readonly headings: Locator
  /** Who the agents ask now, in words. */
  readonly state: Locator
  readonly reason: Locator
  readonly save: Locator
  readonly saved: Locator
  readonly failure: Locator
  readonly notReady: Locator
  readonly daily: Locator
  readonly monthly: Locator
  readonly saveLimits: Locator
  readonly limitsSaved: Locator
  readonly limitsFailure: Locator

  constructor(private readonly page: Page) {
    this.headings = page.getByRole('heading', { level: 2 })
    this.state = page.getByTestId('agent-ai-state')
    this.reason = page.getByTestId('agent-ai-reason')
    this.save = page.getByTestId('agent-ai-save')
    this.saved = page.getByTestId('agent-ai-saved')
    this.failure = page.getByTestId('agent-ai-failure')
    this.notReady = page.getByTestId('agent-ai-notready')
    this.daily = page.getByTestId('agent-limit-daily-field').locator('input')
    this.monthly = page.getByTestId('agent-limit-monthly-field').locator('input')
    this.saveLimits = page.getByTestId('agent-limits-save')
    this.limitsSaved = page.getByTestId('agent-limits-saved')
    this.limitsFailure = page.getByTestId('agent-limits-failure')
  }

  /** The radio button of where the agents get their AI: `shared`, `own` or `off`. */
  source(key: string): Locator {
    return this.page.getByTestId(`source-${key}`).getByRole('radio')
  }

  /** The option of one provider in the choice of their own, by its key such as `anthropic`. */
  provider(key: string): Locator {
    return this.page.getByTestId(`pick-${key}`)
  }

  /** The model the agents ask, which can differ from the one the provider is set up with. */
  get model(): Locator {
    return this.page.getByRole('combobox', { name: 'Model for the agents' })
  }

  /** Opens the list of models, which the field under the combobox takes the click for. */
  async openModels(): Promise<void> {
    await this.page.locator('.v-field', { has: this.model }).click()
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/agents')
  }
}
