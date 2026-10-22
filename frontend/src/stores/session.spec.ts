import { createPinia, setActivePinia } from 'pinia'

import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import * as passkeysApi from '@/api/passkeys'
import { useSessionStore } from '@/stores/session'
import * as webauthn from '@/webauthn'

const info = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }
const notSignedIn = () => new ApiError(401, "You're not signed in.", 'unauthenticated')
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

describe('session store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  describe('restore', () => {
    it('knows nothing until it has asked', () => {
      const store = useSessionStore()
      expect(store.known).toBe(false)
      expect(store.signedIn).toBe(false)
    })

    it('finds a sign-in that is still good', async () => {
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
      vi.spyOn(authApi, 'fetchSession').mockResolvedValue(info)
      const store = useSessionStore()
      await store.restore()
      expect(store).toMatchObject({
        known: true,
        signedIn: true,
        username: 'admin',
        csrfToken: 'a-token',
        setupRequired: false,
        error: null,
      })
    })

    it('finds nobody signed in', async () => {
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
      vi.spyOn(authApi, 'fetchSession').mockRejectedValue(notSignedIn())
      const store = useSessionStore()
      await store.restore()
      expect(store).toMatchObject({ known: true, signedIn: false, setupRequired: false })
    })

    it('does not ask who is signed in on a fresh install, which has no account', async () => {
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(true)
      const session = vi.spyOn(authApi, 'fetchSession')
      const store = useSessionStore()
      await store.restore()
      expect(store).toMatchObject({ known: true, signedIn: false, setupRequired: true })
      expect(session).not.toHaveBeenCalled()
    })

    it.each([
      ['setup status', () => vi.spyOn(authApi, 'fetchSetupRequired')],
      ['session', () => vi.spyOn(authApi, 'fetchSession')],
    ])('keeps the error when the %s can’t be read, and stays unsure', async (_name, spy) => {
      vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
      spy().mockRejectedValue(offline())
      const store = useSessionStore()
      await store.restore()
      expect(store.known).toBe(false)
      expect(store.error).toBe("Can't reach AresGate.")
    })

    it('forgets an earlier error when it asks again', async () => {
      const setup = vi.spyOn(authApi, 'fetchSetupRequired').mockRejectedValueOnce(offline())
      setup.mockResolvedValue(true)
      const store = useSessionStore()
      await store.restore()
      await store.restore()
      expect(store).toMatchObject({ known: true, error: null })
    })
  })

  describe('setting up and signing in', () => {
    it('is signed in after setting up', async () => {
      const setUp = vi.spyOn(authApi, 'setUp').mockResolvedValue(info)
      const store = useSessionStore()
      store.setupRequired = true
      const setup = { code: 'K7QD-3MWX-9HPA', username: 'admin', password: 'a long enough phrase' }
      await store.setUp(setup)
      expect(setUp).toHaveBeenCalledWith(setup)
      expect(store).toMatchObject({ known: true, signedIn: true, setupRequired: false })
    })

    it('is signed in after signing in, and the sign-in is no longer over', async () => {
      const logIn = vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      store.expired = true
      const credentials = { username: 'admin', password: 'a long enough phrase' }
      await store.logIn(credentials)
      expect(logIn).toHaveBeenCalledWith(credentials)
      expect(store).toMatchObject({ signedIn: true, expired: false, csrfToken: 'a-token' })
    })

    it('is not signed in by a password that needs a second step, and hands back the challenge', async () => {
      vi.spyOn(authApi, 'logIn').mockResolvedValue({
        two_factor_required: true,
        challenge: 'a-challenge',
      })
      const store = useSessionStore()
      await expect(store.logIn({ username: 'admin', password: 'x' })).resolves.toBe('a-challenge')
      expect(store.signedIn).toBe(false)
    })

    it('has nothing to hand back when the password signed in', async () => {
      vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      await expect(store.logIn({ username: 'admin', password: 'x' })).resolves.toBeNull()
    })

    it('is signed in once a code finishes the second step', async () => {
      const logInWithCode = vi.spyOn(authApi, 'logInWithCode').mockResolvedValue(info)
      const store = useSessionStore()
      store.expired = true
      await store.logInWithCode('a-challenge', '123456')
      expect(logInWithCode).toHaveBeenCalledWith('a-challenge', '123456')
      expect(store).toMatchObject({ signedIn: true, expired: false, csrfToken: 'a-token' })
    })

    it('stays signed out when the code is wrong', async () => {
      vi.spyOn(authApi, 'logInWithCode').mockRejectedValue(
        new ApiError(401, "That code isn't right.", 'unauthenticated'),
      )
      const store = useSessionStore()
      await expect(store.logInWithCode('a-challenge', '000000')).rejects.toThrow('code')
      expect(store.signedIn).toBe(false)
    })

    it('stays signed out when signing in fails', async () => {
      vi.spyOn(authApi, 'logIn').mockRejectedValue(
        new ApiError(401, 'Incorrect.', 'unauthenticated'),
      )
      const store = useSessionStore()
      await expect(store.logIn({ username: 'a', password: 'b' })).rejects.toThrow('Incorrect.')
      expect(store.signedIn).toBe(false)
    })
  })

  describe('logInWithPasskey', () => {
    const options = { challenge: 'AAAA' } as PublicKeyCredentialRequestOptionsJSON
    const signed = {
      id: 'AAAA',
      rawId: 'AAAA',
      type: 'public-key',
      response: { clientDataJSON: 'BBBB', authenticatorData: 'CCCC', signature: 'DDDD' },
      clientExtensionResults: {},
    } satisfies AuthenticationResponseJSON

    it('is signed in once the device signs what the API asked for', async () => {
      const start = vi
        .spyOn(passkeysApi, 'startPasskeySignIn')
        .mockResolvedValue({ challenge_id: 'an-id', options })
      const get = vi.spyOn(webauthn, 'getPasskey').mockResolvedValue(signed)
      const finish = vi.spyOn(passkeysApi, 'logInWithPasskey').mockResolvedValue(info)
      const store = useSessionStore()
      store.expired = true
      await store.logInWithPasskey()
      expect(start).toHaveBeenCalledOnce()
      expect(get).toHaveBeenCalledWith(options)
      expect(finish).toHaveBeenCalledWith('an-id', signed)
      expect(store).toMatchObject({ signedIn: true, expired: false, csrfToken: 'a-token' })
    })

    it('stays signed out, and sends nothing, when the device is cancelled', async () => {
      vi.spyOn(passkeysApi, 'startPasskeySignIn').mockResolvedValue({
        challenge_id: 'an-id',
        options,
      })
      vi.spyOn(webauthn, 'getPasskey').mockRejectedValue(new webauthn.PasskeyError('Cancelled.'))
      const finish = vi.spyOn(passkeysApi, 'logInWithPasskey')
      const store = useSessionStore()
      await expect(store.logInWithPasskey()).rejects.toThrow('Cancelled.')
      expect(store.signedIn).toBe(false)
      expect(finish).not.toHaveBeenCalled()
    })

    it('stays signed out when the API will not accept the passkey', async () => {
      vi.spyOn(passkeysApi, 'startPasskeySignIn').mockResolvedValue({
        challenge_id: 'an-id',
        options,
      })
      vi.spyOn(webauthn, 'getPasskey').mockResolvedValue(signed)
      vi.spyOn(passkeysApi, 'logInWithPasskey').mockRejectedValue(
        new ApiError(401, "That passkey didn't work.", 'unauthenticated'),
      )
      const store = useSessionStore()
      await expect(store.logInWithPasskey()).rejects.toThrow('passkey')
      expect(store.signedIn).toBe(false)
    })
  })

  describe('logOut', () => {
    async function signedIn() {
      vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      await store.logIn({ username: 'admin', password: 'x' })
      return store
    }

    it('ends the sign-in with its security token', async () => {
      const store = await signedIn()
      const logOut = vi.spyOn(authApi, 'logOut').mockResolvedValue()
      await store.logOut()
      expect(logOut).toHaveBeenCalledWith('a-token')
      expect(store).toMatchObject({ signedIn: false, username: null, csrfToken: null })
    })

    it('is done when the sign-in was over already', async () => {
      const store = await signedIn()
      vi.spyOn(authApi, 'logOut').mockRejectedValue(notSignedIn())
      await store.logOut()
      expect(store.signedIn).toBe(false)
    })

    it('stays signed in, and says why, when the API can’t be reached', async () => {
      const store = await signedIn()
      vi.spyOn(authApi, 'logOut').mockRejectedValue(offline())
      await expect(store.logOut()).rejects.toThrow("Can't reach AresGate.")
      expect(store.signedIn).toBe(true)
    })

    it('has nothing to tell the API when nobody is signed in', async () => {
      const logOut = vi.spyOn(authApi, 'logOut')
      const store = useSessionStore()
      await store.logOut()
      expect(logOut).not.toHaveBeenCalled()
    })
  })

  describe('call', () => {
    it('returns what the call returns', async () => {
      const store = useSessionStore()
      await expect(store.call(() => Promise.resolve(42))).resolves.toBe(42)
    })

    it('notes that the sign-in is over when the API says nobody is signed in', async () => {
      vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      await store.logIn({ username: 'admin', password: 'x' })
      await expect(store.call(() => Promise.reject(notSignedIn()))).rejects.toThrow(
        "You're not signed in.",
      )
      expect(store).toMatchObject({ signedIn: false, expired: true })
    })

    it('leaves the sign-in alone when the call fails for another reason', async () => {
      vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      await store.logIn({ username: 'admin', password: 'x' })
      await expect(store.call(() => Promise.reject(offline()))).rejects.toThrow('reach')
      await expect(store.call(() => Promise.reject(new Error('odd')))).rejects.toThrow('odd')
      expect(store).toMatchObject({ signedIn: true, expired: false })
    })
  })

  describe('change', () => {
    async function signedIn() {
      vi.spyOn(authApi, 'logIn').mockResolvedValue(info)
      const store = useSessionStore()
      await store.logIn({ username: 'admin', password: 'x' })
      return store
    }

    it('gives the call the security token, and returns what it returns', async () => {
      const store = await signedIn()
      const request = vi.fn().mockResolvedValue(42)
      await expect(store.change(request)).resolves.toBe(42)
      expect(request).toHaveBeenCalledWith('a-token')
    })

    it('gives it no token when nobody is signed in, and the API refuses', async () => {
      const store = useSessionStore()
      const request = vi.fn().mockRejectedValue(new ApiError(403, 'No token.', 'forbidden'))
      await expect(store.change(request)).rejects.toThrow('No token.')
      expect(request).toHaveBeenCalledWith('')
    })

    it('notes that the sign-in is over when the API says nobody is signed in', async () => {
      const store = await signedIn()
      await expect(store.change(() => Promise.reject(notSignedIn()))).rejects.toThrow('signed in')
      expect(store).toMatchObject({ signedIn: false, expired: true })
    })

    it('leaves the sign-in alone when the API refuses for another reason', async () => {
      const store = await signedIn()
      const refused = new ApiError(403, "That isn't right.", 'forbidden')
      await expect(store.change(() => Promise.reject(refused))).rejects.toThrow('right')
      expect(store).toMatchObject({ signedIn: true, expired: false })
    })
  })
})
