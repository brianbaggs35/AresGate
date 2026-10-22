import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from '@/App.vue'
import { buildVuetify } from '@/plugins/vuetify'
import { buildRouter } from '@/router'
import { guardRoutes } from '@/router/guard'

export function mountApp(selector = '#app') {
  const app = createApp(App)
  const router = buildRouter()
  guardRoutes(router)
  app.use(createPinia()).use(router).use(buildVuetify())
  app.mount(selector)
  return app
}

mountApp()
