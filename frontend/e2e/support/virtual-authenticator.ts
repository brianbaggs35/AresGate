import type { CDPSession, Page } from '@playwright/test'

/** A passkey the virtual device holds, as far as a test cares. */
export interface HeldPasskey {
  /** The server name the passkey is for. */
  rpId: string
  /** Whether it can be offered without the person saying which account, as AresGate needs. */
  discoverable: boolean
  /** How many times it has signed. */
  signCount: number
}

/**
 * A passkey device made of software: Chromium's virtual authenticator, which unlocks itself the
 * way a laptop with a fingerprint reader would, with no prompt for a test to click through.
 * Only Chromium has one, and a test that asks for it sets one up on its own page.
 */
export class VirtualAuthenticator {
  private constructor(
    private readonly session: CDPSession,
    private readonly authenticatorId: string,
  ) {}

  static async attach(page: Page): Promise<VirtualAuthenticator> {
    const session = await page.context().newCDPSession(page)
    await session.send('WebAuthn.enable')
    const { authenticatorId } = await session.send('WebAuthn.addVirtualAuthenticator', {
      options: {
        protocol: 'ctap2',
        transport: 'internal',
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        // Answers its own "touch the key" prompt.
        automaticPresenceSimulation: true,
      },
    })
    return new VirtualAuthenticator(session, authenticatorId)
  }

  /** The passkeys on the device. */
  async passkeys(): Promise<HeldPasskey[]> {
    const { credentials } = await this.session.send('WebAuthn.getCredentials', {
      authenticatorId: this.authenticatorId,
    })
    return credentials.map((credential) => ({
      rpId: credential.rpId ?? '',
      discoverable: credential.isResidentCredential,
      signCount: credential.signCount,
    }))
  }

  /** Whether the person at the device can unlock it. When they can't, as when a finger isn't
   * recognised, the browser says the passkey was refused. */
  async setUnlockable(unlockable: boolean): Promise<void> {
    await this.session.send('WebAuthn.setUserVerified', {
      authenticatorId: this.authenticatorId,
      isUserVerified: unlockable,
    })
  }

  async detach(): Promise<void> {
    await this.session.send('WebAuthn.removeVirtualAuthenticator', {
      authenticatorId: this.authenticatorId,
    })
    await this.session.send('WebAuthn.disable')
    await this.session.detach()
  }
}
