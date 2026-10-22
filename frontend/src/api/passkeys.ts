import type { SessionInfo } from '@/api/auth'
import { apiGet, apiPost } from '@/api/client'

/** A passkey on the account. Nothing secret: the private key never leaves the device. */
export interface Passkey {
  id: string
  /** What the person called it, such as "Work laptop". */
  name: string
  created_at: string
  last_used_at: string | null
}

/** What a device is asked to make or sign, and the id to send its answer back with. `options`
 * is in the form the browser's `parseCreationOptionsFromJSON` and
 * `parseRequestOptionsFromJSON` take. */
export interface PasskeyChallenge<Options> {
  challenge_id: string
  options: Options
}

/** What the browser's `PublicKeyCredential.toJSON()` gives back. */
export type PasskeyAnswer = RegistrationResponseJSON | AuthenticationResponseJSON

export function fetchPasskeys(): Promise<Passkey[]> {
  return apiGet<Passkey[]>('/auth/passkeys')
}

/** Asks what a device should make a passkey from. It needs the password. */
export function startAddingPasskey(
  password: string,
  csrfToken: string,
): Promise<PasskeyChallenge<PublicKeyCredentialCreationOptionsJSON>> {
  return apiPost('/auth/passkeys/options', { password }, csrfToken)
}

/** Keeps the passkey that a device made from the options above. */
export function addPasskey(
  challengeId: string,
  credential: PasskeyAnswer,
  name: string,
  csrfToken: string,
): Promise<Passkey> {
  return apiPost('/auth/passkeys', { challenge_id: challengeId, credential, name }, csrfToken)
}

/** Forgets a passkey. It needs the password. */
export async function removePasskey(
  id: string,
  password: string,
  csrfToken: string,
): Promise<void> {
  await apiPost<undefined>(
    `/auth/passkeys/${encodeURIComponent(id)}/remove`,
    { password },
    csrfToken,
  )
}

/** Asks what a device should sign to sign in. Nobody has said who they are yet. */
export function startPasskeySignIn(): Promise<
  PasskeyChallenge<PublicKeyCredentialRequestOptionsJSON>
> {
  return apiPost('/auth/login/passkey/options')
}

/** Signs in with a device's answer to the options above. */
export function logInWithPasskey(
  challengeId: string,
  credential: PasskeyAnswer,
): Promise<SessionInfo> {
  return apiPost('/auth/login/passkey', { challenge_id: challengeId, credential })
}
