import * as client from '@/api/client'
import * as passkeys from '@/api/passkeys'

const answer = {
  id: 'AAAA',
  rawId: 'AAAA',
  type: 'public-key',
  response: {
    clientDataJSON: 'BBBB',
    attestationObject: 'CCCC',
    authenticatorData: 'DDDD',
    publicKeyAlgorithm: -7,
    transports: ['internal'],
  },
  clientExtensionResults: {},
} satisfies RegistrationResponseJSON

describe('passkeys API', () => {
  it('lists the passkeys', async () => {
    const list = [
      { id: 'a', name: 'Laptop', created_at: '2026-01-01T00:00:00Z', last_used_at: null },
    ]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(list)
    await expect(passkeys.fetchPasskeys()).resolves.toEqual(list)
    expect(get).toHaveBeenCalledWith('/auth/passkeys')
  })

  it('asks what to make a passkey from, with the password and the security token', async () => {
    const challenge = { challenge_id: 'an-id', options: { challenge: 'x' } }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(challenge)
    await expect(passkeys.startAddingPasskey('a long enough phrase', 'a-token')).resolves.toEqual(
      challenge,
    )
    expect(post).toHaveBeenCalledWith(
      '/auth/passkeys/options',
      { password: 'a long enough phrase' },
      'a-token',
    )
  })

  it('keeps the passkey a device made, under a name', async () => {
    const kept = { id: 'a', name: 'Laptop', created_at: '2026-01-01T00:00:00Z', last_used_at: null }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(kept)
    await expect(passkeys.addPasskey('an-id', answer, 'Laptop', 'a-token')).resolves.toEqual(kept)
    expect(post).toHaveBeenCalledWith(
      '/auth/passkeys',
      { challenge_id: 'an-id', credential: answer, name: 'Laptop' },
      'a-token',
    )
  })

  it('removes a passkey with the password', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)
    await passkeys.removePasskey('some/id', 'a long enough phrase', 'a-token')
    expect(post).toHaveBeenCalledWith(
      '/auth/passkeys/some%2Fid/remove',
      { password: 'a long enough phrase' },
      'a-token',
    )
  })

  it('asks what to sign without saying who is signing in', async () => {
    const challenge = { challenge_id: 'an-id', options: { challenge: 'x' } }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(challenge)
    await expect(passkeys.startPasskeySignIn()).resolves.toEqual(challenge)
    expect(post).toHaveBeenCalledWith('/auth/login/passkey/options')
  })

  it('signs in with what the device signed', async () => {
    const info = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(info)
    await expect(passkeys.logInWithPasskey('an-id', answer)).resolves.toEqual(info)
    expect(post).toHaveBeenCalledWith('/auth/login/passkey', {
      challenge_id: 'an-id',
      credential: answer,
    })
  })
})
