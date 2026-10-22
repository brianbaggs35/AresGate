import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalizedLoaded,
  type RouteRecordRaw,
  type Router,
  type RouterHistory,
} from 'vue-router'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: 'Overview' },
  },
  {
    path: '/:path(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: 'Page not found' },
  },
]

/** The title a route gives its page, if it gives one. */
export function pageTitle(route: Pick<RouteLocationNormalizedLoaded, 'meta'>): string | undefined {
  return typeof route.meta.title === 'string' ? route.meta.title : undefined
}

export function buildRouter(history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({ history, routes })
  router.afterEach((to) => {
    const title = pageTitle(to)
    document.title = title ? `${title} · AresGate` : 'AresGate'
  })
  return router
}
