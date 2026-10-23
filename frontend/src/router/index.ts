import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalizedLoaded,
  type RouteRecordRaw,
  type Router,
  type RouterHistory,
} from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** The page's name, shown in the bar and the browser's tab. */
    title?: string
    /** Open to someone who isn't signed in, and shown without the menu. */
    public?: boolean
  }
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: 'Overview' },
  },
  {
    // The list, and a page for each integration. Both belong to the one place in the menu.
    path: '/integrations',
    children: [
      {
        path: '',
        name: 'integrations',
        component: () => import('@/views/IntegrationsView.vue'),
        meta: { title: 'Integrations' },
      },
      {
        path: ':key',
        name: 'integration',
        component: () => import('@/views/IntegrationView.vue'),
        meta: { title: 'Integrations' },
      },
    ],
  },
  {
    path: '/security',
    name: 'security',
    component: () => import('@/views/SecurityView.vue'),
    meta: { title: 'Security' },
  },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('@/views/SetupView.vue'),
    meta: { title: 'Set up', public: true },
  },
  {
    path: '/sign-in',
    name: 'sign-in',
    component: () => import('@/views/SignInView.vue'),
    meta: { title: 'Sign in', public: true },
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
