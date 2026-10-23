import { apiGet, apiPost } from '@/api/client'

/** A browser that is signed in to the account. */
export interface SignIn {
  id: string
  /** Whether it is the browser asking. */
  current: boolean
  address: string | null
  /** What the browser called itself. Sign-ins from before this was kept have none. */
  user_agent: string | null
  started_at: string
  last_seen_at: string
  /** When it ends if nothing more happens. */
  expires_at: string
}

/** How many sign-ins a change ended. */
export interface Ended {
  ended: number
}

/** Changes the password. It needs the current one, and ends every other sign-in. */
export function changePassword(
  currentPassword: string,
  newPassword: string,
  csrfToken: string,
): Promise<Ended> {
  return apiPost<Ended>(
    '/auth/password',
    { current_password: currentPassword, new_password: newPassword },
    csrfToken,
  )
}

export function fetchSignIns(): Promise<SignIn[]> {
  return apiGet<SignIn[]>('/auth/sessions')
}

/** Signs one other browser out. */
export async function endSignIn(id: string, csrfToken: string): Promise<void> {
  await apiPost<undefined>(`/auth/sessions/${encodeURIComponent(id)}/end`, undefined, csrfToken)
}

/** Signs out every browser but this one. */
export function endOtherSignIns(csrfToken: string): Promise<Ended> {
  return apiPost<Ended>('/auth/sessions/end-others', undefined, csrfToken)
}
