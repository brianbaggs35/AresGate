import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, type RouteLocationRaw } from 'vue-router'

import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import { buildRouter } from '@/router'
import { guardRoutes, landingPage } from '@/router/guard'
import { useSessionStore } from '@/stores/session'

const info = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }

function guarded() {
  setActivePinia(createPinia())
  const router = buildRouter(createMemoryHistory())
  guardRoutes(router)
  return router
}

const state = {
  freshInstall: () => {
    vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(true)
  },
  signedOut: () => {
    vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
    vi.spyOn(authApi, 'fetchSession').mockRejectedValue(
      new ApiError(401, "You're not signed in.", 'unauthenticated'),
    )
  },
  signedIn: () => {
    vi.spyOn(authApi, 'fetchSetupRequired').mockResolvedValue(false)
    vi.spyOn(authApi, 'fetchSession').mockResolvedValue(info)
  },
}

async function goTo(path: string) {
  const router = guarded()
  await router.push(path)
  return router.currentRoute.value
}

describe('route guard', () => {
  it('sends everyone to setting up while there is no account', async () => {
    state.freshInstall()
    expect((await goTo('/')).name).toBe('setup')
    expect((await goTo('/sign-in')).name).toBe('setup')
    expect((await goTo('/setup')).name).toBe('setup')
  })

  it('sends someone who is not signed in to the sign-in page, and remembers where they were going', async () => {
    state.signedOut()
    const route = await goTo('/settings/account?tab=activity')
    expect(route.name).toBe('sign-in')
    expect(route.query).toEqual({ next: '/settings/account?tab=activity' })
  })

  it('has nothing to remember for the front page', async () => {
    state.signedOut()
    const route = await goTo('/')
    expect(route.name).toBe('sign-in')
    expect(route.query).toEqual({})
  })

  it("doesn't tell someone who isn't signed in which addresses exist", async () => {
    state.signedOut()
    expect((await goTo('/no/such/page')).name).toBe('sign-in')
  })

  it('lets someone who is not signed in see the sign-in page', async () => {
    state.signedOut()
    expect((await goTo('/sign-in')).name).toBe('sign-in')
  })

  it('sends them away from setting up once there is an account', async () => {
    state.signedOut()
    expect((await goTo('/setup')).name).toBe('sign-in')
    state.signedIn()
    expect((await goTo('/setup')).name).toBe('home')
  })

  it('lets someone who is signed in see every page, and sends them away from the sign-in page', async () => {
    state.signedIn()
    expect((await goTo('/')).name).toBe('home')
    expect((await goTo('/settings/account')).name).toBe('settings-account')
    expect((await goTo('/no/such/page')).name).toBe('not-found')
    expect((await goTo('/sign-in')).name).toBe('home')
  })

  it('asks the API once, not on every move', async () => {
    state.signedIn()
    const router = guarded()
    await router.push('/')
    await router.push('/settings/account')
    expect(authApi.fetchSetupRequired).toHaveBeenCalledTimes(1)
  })

  it('lets the page appear, and asks again on the next move, when the API can’t say', async () => {
    const setup = vi
      .spyOn(authApi, 'fetchSetupRequired')
      .mockRejectedValueOnce(new ApiError(0, "Can't reach AresGate.", 'offline'))
    setup.mockResolvedValue(false)
    vi.spyOn(authApi, 'fetchSession').mockResolvedValue(info)
    const router = guarded()
    await router.push('/settings/account')
    expect(router.currentRoute.value.name).toBe('settings-account')
    expect(useSessionStore().error).toBe("Can't reach AresGate.")
    await router.push('/')
    expect(useSessionStore().error).toBeNull()
    expect(router.currentRoute.value.name).toBe('home')
  })
})

describe('landingPage', () => {
  it.each([
    ['/settings/account', '/settings/account'],
    ['/settings/account?tab=activity#top', '/settings/account?tab=activity#top'],
  ])('goes back to %s', (next, landing) => {
    expect(landingPage({ next })).toBe(landing)
  })

  it.each([
    ['nothing', {}],
    ['a list', { next: ['/settings/account', '/'] }],
    ['an empty address', { next: '' }],
    ['a relative address', { next: 'settings/account' }],
    ['another site', { next: 'https://example.com/' }],
    ['another site without a scheme', { next: '//example.com/' }],
    ['another site with a backslash', { next: '/\\example.com/' }],
  ])('goes home given %s', (_name, query) => {
    const landing: RouteLocationRaw = landingPage(query)
    expect(landing).toEqual({ name: 'home' })
  })
})
