/** The browser's WebAuthn API, which asks a device to make or use a passkey: a fingerprint, a
 * face or a PIN unlocks a key that never leaves the device. */

import type { PasskeyAnswer } from '@/api/passkeys'

/** Why a passkey couldn't be made or used, in words for the person at the screen. */
export class PasskeyError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PasskeyError'
  }
}

/** Whether this browser can make and use passkeys. The JSON helpers are what the API's options
 * are made for, and every browser that has passkeys has had them since 2024. */
export function passkeysSupported(): boolean {
  return (
    'PublicKeyCredential' in window &&
    typeof PublicKeyCredential.parseCreationOptionsFromJSON === 'function' &&
    typeof PublicKeyCredential.parseRequestOptionsFromJSON === 'function' &&
    // Browsers leave it out on a page that isn't served over HTTPS.
    'credentials' in navigator
  )
}

/** The browser refuses in a few ways that mean different things to the person. */
function explain(error: unknown, making: boolean): PasskeyError {
  if (error instanceof PasskeyError) return error
  const name = error instanceof DOMException ? error.name : ''
  const doing = making ? 'Making' : 'Using'
  switch (name) {
    case 'NotAllowedError':
      return new PasskeyError(`${doing} the passkey was cancelled or timed out. Try again.`)
    case 'InvalidStateError':
      return new PasskeyError('This device already has a passkey for your account.')
    case 'SecurityError':
      return new PasskeyError(
        "A passkey can't be used at this address. Open AresGate by its server name, such as aresgate.example.com, not by an IP address.",
      )
    case 'NotSupportedError':
      return new PasskeyError("This device can't make a passkey that it unlocks itself.")
    default:
      return new PasskeyError(`Your browser couldn't ${making ? 'make' : 'use'} a passkey.`)
  }
}

/** Asks the device to make a passkey, which it unlocks itself, to be kept on the account. */
export async function createPasskey(
  options: PublicKeyCredentialCreationOptionsJSON,
): Promise<PasskeyAnswer> {
  try {
    const credential = await navigator.credentials.create({
      publicKey: PublicKeyCredential.parseCreationOptionsFromJSON(options),
    })
    if (!(credential instanceof PublicKeyCredential)) throw new PasskeyError('No passkey was made.')
    return credential.toJSON()
  } catch (creationError) {
    throw explain(creationError, true)
  }
}

/** Asks the device to sign in with one of its passkeys for this address. */
export async function getPasskey(
  options: PublicKeyCredentialRequestOptionsJSON,
): Promise<PasskeyAnswer> {
  try {
    const credential = await navigator.credentials.get({
      publicKey: PublicKeyCredential.parseRequestOptionsFromJSON(options),
    })
    if (!(credential instanceof PublicKeyCredential)) throw new PasskeyError('No passkey was used.')
    return credential.toJSON()
  } catch (usingError) {
    throw explain(usingError, false)
  }
}
