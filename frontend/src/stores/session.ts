import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/api/auth'
import { ApiError, errorMessage } from '@/api/client'

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

  async function logIn(credentials: authApi.Credentials) {
    adopt(await authApi.logIn(credentials))
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
    logOut,
    call,
  }
})
