import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/api/auth'
import { ApiError, errorMessage } from '@/api/client'
import * as passkeysApi from '@/api/passkeys'
import { getPasskey } from '@/webauthn'

const isUnauthenticated = (error: unknown) => error instanceof ApiError && error.status === 401

export const useSessionStore = defineStore('session', () => {
  /** Whether the API has been asked who is signed in yet. */
  const known = ref(false)
  /** True on a fresh install, which has no account until it is set up. */
  const setupRequired = ref(false)
  const username = ref<string | null>(null)
  const csrfToken = ref<string | null>(null)
  /** Set when a call found the sign-in over, so the sign-in page can say so. */
  const expired = ref(false)
  /** Why the API couldn't say who is signed in, if it couldn't. */
  const error = ref<string | null>(null)

  const signedIn = computed(() => username.value !== null)

  function adopt(info: authApi.SessionInfo) {
    known.value = true
    setupRequired.value = false
    expired.value = false
    username.value = info.username
    csrfToken.value = info.csrf_token
  }

  function forget() {
    username.value = null
    csrfToken.value = null
  }

  /** Asks the API whether this is a fresh install and who, if anyone, is signed in. */
  async function restore() {
    error.value = null
    try {
      setupRequired.value = await authApi.fetchSetupRequired()
      if (setupRequired.value) {
        forget()
      } else {
        try {
          adopt(await authApi.fetchSession())
        } catch (sessionError) {
          if (!isUnauthenticated(sessionError)) throw sessionError
          forget()
        }
      }
      known.value = true
    } catch (restoreError) {
      error.value = errorMessage(restoreError)
    }
  }

  async function setUp(setup: authApi.Setup) {
    adopt(await authApi.setUp(setup))
  }

  /** Signs in. An account with a second step isn't signed in by its password alone: then this
   * returns the challenge to send back with a code (see `logInWithCode`), and otherwise null. */
  async function logIn(credentials: authApi.Credentials): Promise<string | null> {
    const result = await authApi.logIn(credentials)
    if (authApi.isChallenge(result)) return result.challenge
    adopt(result)
    return null
  }

  /** Finishes signing in with a code from the authenticator app or a recovery code. */
  async function logInWithCode(challenge: string, code: string) {
    adopt(await authApi.logInWithCode(challenge, code))
  }

  /** Signs in with a passkey: the device is asked to unlock one of its passkeys for this address,
   * which says whose it is. A passkey is the password and the second step in one. */
  async function logInWithPasskey() {
    const { challenge_id: challengeId, options } = await passkeysApi.startPasskeySignIn()
    const credential = await getPasskey(options)
    adopt(await passkeysApi.logInWithPasskey(challengeId, credential))
  }

  /** Ends the sign-in. If it was over already, that's what was wanted. */
  async function logOut() {
    if (csrfToken.value) {
      try {
        await authApi.logOut(csrfToken.value)
      } catch (logOutError) {
        if (!isUnauthenticated(logOutError)) throw logOutError
      }
    }
    forget()
  }

  /** Runs a call that needs a sign-in. If the answer is that there isn't one any more, because
   * it ended while the page sat open, the store notes it so the app can go to the sign-in page. */
  async function call<T>(request: () => Promise<T>): Promise<T> {
    try {
      return await request()
    } catch (callError) {
      if (isUnauthenticated(callError)) {
        forget()
        expired.value = true
      }
      throw callError
    }
  }

  /** Runs a change that needs the sign-in's security token, as `call` does. */
  function change<T>(request: (csrfToken: string) => Promise<T>): Promise<T> {
    return call(() => request(csrfToken.value ?? ''))
  }

  return {
    known,
    setupRequired,
    username,
    csrfToken,
    expired,
    error,
    signedIn,
    restore,
    setUp,
    logIn,
    logInWithCode,
    logInWithPasskey,
    logOut,
    call,
    change,
  }
})
