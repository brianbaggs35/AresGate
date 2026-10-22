import { apiGet, apiPost } from '@/api/client'

/** Who is signed in. */
export interface SessionInfo {
  username: string
  /** Sent back with every change, to show it came from AresGate's own pages. */
  csrf_token: string
  expires_at: string
}

/** What a right password earns on an account with a second step: not a sign-in yet, but a
 * challenge to send back with a code from the authenticator app or a recovery code. */
export interface TwoFactorChallenge {
  two_factor_required: true
  challenge: string
}

export function isChallenge(
  result: SessionInfo | TwoFactorChallenge,
): result is TwoFactorChallenge {
  return 'two_factor_required' in result
}

export interface Credentials {
  username: string
  password: string
}

export interface Setup extends Credentials {
  /** The one-time code from the container's log. */
  code: string
}

export async function fetchSetupRequired(): Promise<boolean> {
  const status = await apiGet<{ setup_required: boolean }>('/setup/status')
  return status.setup_required
}

/** Fails with a 401 unless someone is signed in. */
export function fetchSession(): Promise<SessionInfo> {
  return apiGet<SessionInfo>('/auth/session')
}

/** Creates the account, and signs in as it. */
export function setUp(setup: Setup): Promise<SessionInfo> {
  return apiPost<SessionInfo>('/setup', setup)
}

export function logIn(credentials: Credentials): Promise<SessionInfo | TwoFactorChallenge> {
  return apiPost<SessionInfo | TwoFactorChallenge>('/auth/login', credentials)
}

/** The second step of signing in, for an account that has an authenticator app. */
export function logInWithCode(challenge: string, code: string): Promise<SessionInfo> {
  return apiPost<SessionInfo>('/auth/login/two-factor', { challenge, code })
}

export async function logOut(csrfToken: string): Promise<void> {
  await apiPost<undefined>('/auth/logout', undefined, csrfToken)
}
