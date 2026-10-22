import {
  createRouter,
  createWebHistory,
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

export function buildRouter(history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({ history, routes })
  router.afterEach((to) => {
    const title = typeof to.meta.title === 'string' ? to.meta.title : undefined
    document.title = title ? `${title} · AresGate` : 'AresGate'
  })
  return router
}
