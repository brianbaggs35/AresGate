import { apiGet, apiPost } from '@/api/client'

/** Who is signed in. */
export interface SessionInfo {
  username: string
  /** Sent back with every change, to show it came from AresGate's own pages. */
  csrf_token: string
  expires_at: string
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

export function logIn(credentials: Credentials): Promise<SessionInfo> {
  return apiPost<SessionInfo>('/auth/login', credentials)
}

export async function logOut(csrfToken: string): Promise<void> {
  await apiPost<undefined>('/auth/logout', undefined, csrfToken)
}
