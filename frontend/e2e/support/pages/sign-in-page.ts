import type { Locator, Page } from '@playwright/test'

import type { Credentials } from '../harness'

/** The page that asks for a username and a password. */
export class SignInPage {
  readonly title: Locator
  readonly username: Locator
  readonly password: Locator
  readonly showPassword: Locator
  readonly submit: Locator
  /** Why a sign-in failed. */
  readonly error: Locator
  /** Says the last sign-in ended while the page was open. */
  readonly endedNotice: Locator
  /** The second step, for an account with an authenticator app. */
  readonly code: Locator
  readonly verify: Locator
  readonly startOver: Locator
  /** The button that signs in with a passkey, for browsers that have them. */
  readonly passkey: Locator

  constructor(private readonly page: Page) {
    this.title = page.getByRole('heading', { level: 1 })
    this.username = page.getByLabel('Username')
    // "Show password" is a button's name, so only the field's own name will do.
    this.password = page.getByLabel('Password', { exact: true })
    this.showPassword = page.getByRole('button', { name: 'Show password' })
    this.submit = page.getByTestId('sign-in')
    this.error = page.getByTestId('sign-in-error')
    this.endedNotice = page.getByTestId('signed-out-notice')
    this.code = page.getByLabel('Code', { exact: true })
    this.verify = page.getByTestId('verify')
    this.startOver = page.getByTestId('start-over')
    this.passkey = page.getByTestId('sign-in-passkey')
  }

  async goto(path = '/sign-in'): Promise<void> {
    await this.page.goto(path)
  }

  async signIn({ username, password }: Credentials): Promise<void> {
    await this.username.fill(username)
    await this.password.fill(password)
    await this.submit.click()
  }

  /** The second step: a code from the authenticator app, or a recovery code. */
  async enterCode(code: string): Promise<void> {
    await this.code.fill(code)
    await this.verify.click()
  }
}
