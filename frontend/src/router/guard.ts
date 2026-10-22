import type { LocationQuery, RouteLocationRaw, Router } from 'vue-router'

import { useSessionStore } from '@/stores/session'

/**
 * Sends people where they can go: to setting up while there is no account, to signing in while
 * they aren't signed in, and away from those pages once they are. It's separate from the routes
 * so a test of a page doesn't have to answer the API's questions about who is signed in.
 */
export function guardRoutes(router: Router): void {
  router.beforeEach(async (to): Promise<true | RouteLocationRaw> => {
    const session = useSessionStore()
    if (!session.known) await session.restore()
    // The API couldn't say. The app explains why and offers to try again.
    if (!session.known) return true

    if (session.setupRequired) return to.name === 'setup' ? true : { name: 'setup' }
    if (to.name === 'setup') return { name: session.signedIn ? 'home' : 'sign-in' }
    if (session.signedIn) return to.name === 'sign-in' ? { name: 'home' } : true
    if (to.meta.public) return true
    return { name: 'sign-in', query: to.fullPath === '/' ? {} : { next: to.fullPath } }
  })
}

/** Where to go after signing in: the page they were sent away from, if it's on this site. */
export function landingPage(query: LocationQuery): RouteLocationRaw {
  const next = query.next
  // A path on this site starts with one slash. Two, or a backslash, would leave it.
  if (typeof next === 'string' && /^\/(?![/\\])/.test(next)) return next
  return { name: 'home' }
}
