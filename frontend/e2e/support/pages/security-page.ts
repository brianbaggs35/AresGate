import { expect, type Locator, type Page } from '@playwright/test'

import { authenticatorCode } from '../totp'

/** The settings page for the account: who is signed in, the password, passkeys and two-step. */
export class SecurityPage {
  readonly accountName: Locator
  readonly signOut: Locator
  /** Why signing out from this page failed. */
  readonly signOutError: Locator

  /** The card for the password: the three fields, the button, and what came of it. */
  readonly passwordCard: Locator
  readonly currentPassword: Locator
  readonly newPassword: Locator
  readonly confirmNewPassword: Locator
  readonly changePassword: Locator
  readonly passwordChanged: Locator
  readonly passwordError: Locator

  /** The card for passkeys: the ones on the account ... */
  readonly passkeysCard: Locator
  readonly passkeyNames: Locator
  readonly passkeyDetails: Locator
  readonly noPasskeys: Locator
  readonly removePasskeyButtons: Locator
  readonly passkeysUnsupported: Locator
  readonly passkeysLoadError: Locator
  /** ... why a change failed ... */
  readonly passkeysError: Locator
  /** ... adding one, and removing one. */
  readonly addPasskey: Locator
  readonly newPasskeyName: Locator
  readonly passkeyPassword: Locator
  readonly createPasskey: Locator
  readonly confirmRemovePasskey: Locator

  /** The card for two-step verification: first what it says about the account ... */
  readonly twoFactorCard: Locator
  readonly twoFactorOff: Locator
  readonly twoFactorOn: Locator
  readonly recoveryCodesLeft: Locator
  readonly recoveryCodesLow: Locator
  readonly twoFactorLoadError: Locator
  readonly twoFactorRetry: Locator
  /** ... why a change failed ... */
  readonly twoFactorError: Locator
  /** ... adding an app ... */
  readonly addApp: Locator
  readonly qrCode: Locator
  readonly openInApp: Locator
  readonly key: Locator
  readonly confirmCode: Locator
  readonly confirm: Locator
  readonly cancel: Locator
  /** ... the recovery codes that are shown once ... */
  readonly recoveryCodeItems: Locator
  readonly copyCodes: Locator
  readonly copyNote: Locator
  readonly codesSaved: Locator
  readonly codesDone: Locator
  /** ... making new ones, and turning it off. */
  readonly renewCodes: Locator
  readonly renewCode: Locator
  readonly renew: Locator
  readonly turnOff: Locator
  readonly turnOffPassword: Locator
  readonly turnOffCode: Locator
  readonly confirmTurnOff: Locator

  constructor(private readonly page: Page) {
    this.accountName = page.getByTestId('account-name')
    this.signOut = page.getByTestId('sign-out-here')
    this.signOutError = page.getByTestId('sign-out-here-error')
    this.passwordCard = page.getByTestId('password-card')
    this.currentPassword = page.getByLabel('Current password', { exact: true })
    this.newPassword = page.getByLabel('New password', { exact: true })
    this.confirmNewPassword = page.getByLabel('Confirm new password', { exact: true })
    this.changePassword = page.getByTestId('change-password')
    this.passwordChanged = page.getByTestId('password-changed')
    this.passwordError = page.getByTestId('password-error')
    this.passkeysCard = page.getByTestId('passkeys-card')
    this.passkeyNames = page.getByTestId('passkey-name')
    this.passkeyDetails = page.getByTestId('passkey-details')
    this.noPasskeys = page.getByTestId('no-passkeys')
    this.removePasskeyButtons = page.getByTestId('remove-passkey')
    this.passkeysUnsupported = page.getByTestId('passkeys-unsupported')
    this.passkeysLoadError = page.getByTestId('passkeys-load-error')
    this.passkeysError = page.getByTestId('passkeys-error')
    this.addPasskey = page.getByTestId('add-passkey')
    this.newPasskeyName = page.getByLabel('Name', { exact: true })
    this.passkeyPassword = page.getByLabel('Password', { exact: true })
    this.createPasskey = page.getByTestId('create-passkey')
    this.confirmRemovePasskey = page.getByTestId('confirm-remove-passkey')
    this.twoFactorCard = page.getByTestId('two-factor-card')
    this.twoFactorOff = page.getByTestId('two-factor-off')
    this.twoFactorOn = page.getByTestId('two-factor-state')
    this.recoveryCodesLeft = page.getByTestId('recovery-codes-left')
    this.recoveryCodesLow = page.getByTestId('recovery-codes-low')
    this.twoFactorLoadError = page.getByTestId('two-factor-load-error')
    this.twoFactorRetry = page.getByTestId('two-factor-retry')
    this.twoFactorError = page.getByTestId('two-factor-error')
    this.addApp = page.getByTestId('add-app')
    this.qrCode = page.getByRole('img', { name: 'QR code for your authenticator app' })
    this.openInApp = page.getByTestId('open-in-app')
    this.key = page.getByTestId('two-factor-key')
    this.confirmCode = page.getByLabel('Code from the app')
    this.confirm = page.getByTestId('confirm')
    this.cancel = page.getByTestId('cancel')
    this.recoveryCodeItems = page.getByTestId('recovery-code')
    this.copyCodes = page.getByTestId('copy-codes')
    this.copyNote = page.getByTestId('copy-note')
    this.codesSaved = page.getByLabel("I've saved these codes")
    this.codesDone = page.getByTestId('codes-done')
    this.renewCodes = page.getByTestId('renew-codes')
    this.renewCode = page.getByLabel('Code', { exact: true })
    this.renew = page.getByTestId('renew')
    this.turnOff = page.getByTestId('turn-off')
    this.turnOffPassword = page.getByLabel('Password', { exact: true })
    this.turnOffCode = page.getByLabel('Code', { exact: true })
    this.confirmTurnOff = page.getByTestId('confirm-turn-off')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/account')
  }

  /** Changes the password the way a person would, typing the new one twice. */
  async changePasswordTo(current: string, next: string): Promise<void> {
    await this.currentPassword.fill(current)
    await this.newPassword.fill(next)
    await this.confirmNewPassword.fill(next)
    await this.changePassword.click()
  }

  /** Adds a passkey the way a person would: a name and the password, then the device unlocks. */
  async addPasskeyNamed(name: string, password: string): Promise<void> {
    await this.addPasskey.click()
    await this.newPasskeyName.fill(name)
    await this.passkeyPassword.fill(password)
    await this.createPasskey.click()
    await expect(this.passkeyNames.filter({ hasText: name })).toBeVisible()
  }

  /**
   * Adds an authenticator app the way a person would, with a code worked out from the key on
   * the page, and saves the recovery codes. Returns the key the app holds and the codes.
   */
  async addAuthenticator(): Promise<{ secret: string; recoveryCodes: string[] }> {
    await this.addApp.click()
    const secret = ((await this.key.textContent()) ?? '').replaceAll(/\s/g, '')
    await this.confirmCode.fill(authenticatorCode(secret))
    await this.confirm.click()
    await expect(this.recoveryCodeItems).toHaveCount(10)
    const recoveryCodes = (await this.recoveryCodeItems.allTextContents()).map((code) =>
      code.trim(),
    )
    await this.codesSaved.check()
    await this.codesDone.click()
    await expect(this.twoFactorOn).toBeVisible()
    return { secret, recoveryCodes }
  }
}
