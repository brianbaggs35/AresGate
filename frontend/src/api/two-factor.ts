import { apiGet, apiPost } from '@/api/client'

export interface TwoFactorStatus {
  enabled: boolean
  recovery_codes_left: number
}

/** A key for an authenticator app, to scan as a QR code or to type in. */
export interface Enrollment {
  secret: string
  /** The `otpauth://` address that the QR code carries. */
  otpauth_uri: string
}

export function fetchTwoFactorStatus(): Promise<TwoFactorStatus> {
  return apiGet<TwoFactorStatus>('/auth/two-factor')
}

/** Makes a key. It counts only once `confirmTwoFactor` has a code from the app. */
export function startTwoFactor(csrfToken: string): Promise<Enrollment> {
  return apiPost<Enrollment>('/auth/two-factor/enroll', undefined, csrfToken)
}

/** Turns the second step on, and returns the recovery codes, which are shown only this once. */
export async function confirmTwoFactor(code: string, csrfToken: string): Promise<string[]> {
  const answer = await apiPost<{ recovery_codes: string[] }>(
    '/auth/two-factor/confirm',
    { code },
    csrfToken,
  )
  return answer.recovery_codes
}

/** Ends the old recovery codes and returns new ones. It needs a current code. */
export async function renewRecoveryCodes(code: string, csrfToken: string): Promise<string[]> {
  const answer = await apiPost<{ recovery_codes: string[] }>(
    '/auth/two-factor/recovery-codes',
    { code },
    csrfToken,
  )
  return answer.recovery_codes
}

/** Turns the second step off. It needs the password and a current code. */
export async function turnOffTwoFactor(
  password: string,
  code: string,
  csrfToken: string,
): Promise<void> {
  await apiPost<undefined>('/auth/two-factor/disable', { password, code }, csrfToken)
}
