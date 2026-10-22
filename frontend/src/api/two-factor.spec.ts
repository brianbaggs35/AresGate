import * as client from '@/api/client'
import * as twoFactor from '@/api/two-factor'

const codes = ['K7QD-3MWX-9HPA', 'ABCD-EFGH-2345']

describe('two-factor API', () => {
  it('reads whether the second step is on', async () => {
    const status = { enabled: true, recovery_codes_left: 7 }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(status)
    await expect(twoFactor.fetchTwoFactorStatus()).resolves.toEqual(status)
    expect(get).toHaveBeenCalledWith('/auth/two-factor')
  })

  it('starts adding an app, with the security token', async () => {
    const enrollment = { secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/AresGate:a' }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(enrollment)
    await expect(twoFactor.startTwoFactor('a-token')).resolves.toEqual(enrollment)
    expect(post).toHaveBeenCalledWith('/auth/two-factor/enroll', undefined, 'a-token')
  })

  it('turns it on with a code from the app, and returns the recovery codes', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ recovery_codes: codes })
    await expect(twoFactor.confirmTwoFactor('123456', 'a-token')).resolves.toEqual(codes)
    expect(post).toHaveBeenCalledWith('/auth/two-factor/confirm', { code: '123456' }, 'a-token')
  })

  it('makes new recovery codes with a code', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ recovery_codes: codes })
    await expect(twoFactor.renewRecoveryCodes('123456', 'a-token')).resolves.toEqual(codes)
    expect(post).toHaveBeenCalledWith(
      '/auth/two-factor/recovery-codes',
      { code: '123456' },
      'a-token',
    )
  })

  it('turns it off with the password and a code', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)
    await twoFactor.turnOffTwoFactor('a long enough phrase', '123456', 'a-token')
    expect(post).toHaveBeenCalledWith(
      '/auth/two-factor/disable',
      { password: 'a long enough phrase', code: '123456' },
      'a-token',
    )
  })
})
