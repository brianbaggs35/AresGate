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
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: 'Dashboard' },
  },
  {
    // The list, and a page for each incident. Both belong to the one place in the menu.
    path: '/incidents',
    children: [
      {
        path: '',
        name: 'incidents',
        component: () => import('@/views/IncidentsView.vue'),
        meta: { title: 'Incidents' },
      },
      {
        path: String.raw`:id(\d+)`,
        name: 'incident',
        component: () => import('@/views/IncidentView.vue'),
        meta: { title: 'Incidents' },
      },
    ],
  },
  {
    // The threats, the kinds of incident that are background, and a page for each kind. All
    // belong to the one place in the menu.
    path: '/threats',
    children: [
      {
        path: '',
        name: 'threats',
        component: () => import('@/views/ThreatsView.vue'),
        meta: { title: 'Threats' },
      },
      {
        path: 'kinds',
        name: 'kinds',
        component: () => import('@/views/KindsView.vue'),
        meta: { title: 'Threats' },
      },
      {
        path: String.raw`kinds/:id(\d+)`,
        name: 'family',
        component: () => import('@/views/FamilyView.vue'),
        meta: { title: 'Threats' },
      },
    ],
  },
  {
    // The chat, and a page for each conversation. Both belong to the one place in the menu.
    path: '/assistant',
    children: [
      {
        path: '',
        name: 'assistant',
        component: () => import('@/views/AssistantView.vue'),
        meta: { title: 'Assistant' },
      },
      {
        path: String.raw`:id(\d+)`,
        name: 'assistant-chat',
        component: () => import('@/views/AssistantView.vue'),
        meta: { title: 'Assistant' },
      },
    ],
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { title: 'Logs' },
  },
  {
    path: '/assets',
    name: 'assets',
    component: () => import('@/views/AssetsView.vue'),
    meta: { title: 'Assets' },
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
    // The list, and a page for each interface. Both belong to the one place in the menu.
    path: '/interfaces',
    children: [
      {
        path: '',
        name: 'interfaces',
        component: () => import('@/views/InterfacesView.vue'),
        meta: { title: 'Interfaces' },
      },
      {
        path: String.raw`:id(\d+)`,
        name: 'interface',
        component: () => import('@/views/InterfaceView.vue'),
        meta: { title: 'Interfaces' },
      },
    ],
  },
  {
    path: '/ai-usage',
    name: 'ai-usage',
    component: () => import('@/views/AiUsageView.vue'),
    meta: { title: 'AI usage' },
  },
  {
    path: '/alerts',
    name: 'alerts',
    component: () => import('@/views/AlertsView.vue'),
    meta: { title: 'Alerts' },
  },
  {
    path: '/status',
    name: 'status',
    component: () => import('@/views/StatusView.vue'),
    meta: { title: 'Status' },
  },
  {
    // The pages of the Settings area share a list (tabs on a phone) and belong to the one place
    // in the menu.
    path: '/settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: 'Settings' },
    children: [
      { path: '', name: 'settings', redirect: { name: 'settings-account' } },
      {
        path: 'account',
        name: 'settings-account',
        component: () => import('@/views/AccountView.vue'),
      },
      {
        path: 'sign-ins',
        name: 'settings-sign-ins',
        component: () => import('@/views/SignInsView.vue'),
      },
      {
        path: 'activity',
        name: 'settings-activity',
        component: () => import('@/views/ActivityView.vue'),
      },
      {
        path: 'verdicts',
        name: 'settings-verdicts',
        component: () => import('@/views/VerdictsView.vue'),
      },
      {
        path: 'noise-filters',
        name: 'settings-noise-filters',
        component: () => import('@/views/NoiseFiltersView.vue'),
      },
      {
        path: 'threat-detection',
        name: 'settings-threat-detection',
        component: () => import('@/views/ThreatSettingsView.vue'),
      },
      {
        path: 'ai',
        name: 'settings-ai',
        component: () => import('@/views/AiSettingsView.vue'),
      },
      {
        path: 'data',
        name: 'settings-data',
        component: () => import('@/views/DataView.vue'),
      },
    ],
  },
  // The Security page became the Settings area's Account page.
  { path: '/security', redirect: { name: 'settings-account' } },
  // AI usage was a page of Settings before it became a place in the menu.
  { path: '/settings/ai-usage', redirect: { name: 'ai-usage' } },
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
