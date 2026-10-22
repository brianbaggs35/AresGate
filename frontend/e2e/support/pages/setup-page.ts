import type { Locator, Page } from '@playwright/test'

import type { Credentials } from '../harness'

/** The two steps that create the account on a fresh install. */
export class SetupPage {
  readonly title: Locator
  /** "Step 1 of 2", or "Step 2 of 2". */
  readonly step: Locator
  readonly code: Locator
  readonly continue: Locator
  readonly username: Locator
  readonly password: Locator
  readonly confirmation: Locator
  readonly back: Locator
  readonly createAccount: Locator
  readonly error: Locator

  constructor(private readonly page: Page) {
    this.title = page.getByRole('heading', { level: 1 })
    this.step = page.getByText(/^Step \d of 2/)
    this.code = page.getByLabel('Setup code')
    this.continue = page.getByTestId('continue')
    this.username = page.getByLabel('Username')
    this.password = page.getByLabel('Password', { exact: true })
    this.confirmation = page.getByLabel('Confirm password', { exact: true })
    this.back = page.getByTestId('back')
    this.createAccount = page.getByTestId('create-account')
    this.error = page.getByTestId('setup-error')
  }

  async goto(path = '/setup'): Promise<void> {
    await this.page.goto(path)
  }

  /** Step one. */
  async enterCode(code: string): Promise<void> {
    await this.code.fill(code)
    await this.continue.click()
  }

  /** Step two. */
  async createAccountWith({ username, password }: Credentials, confirmation = password) {
    await this.username.fill(username)
    await this.password.fill(password)
    await this.confirmation.fill(confirmation)
    await this.createAccount.click()
  }
}
