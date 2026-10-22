import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from '@/App.vue'
import { buildVuetify } from '@/plugins/vuetify'
import { buildRouter } from '@/router'

export function mountApp(selector = '#app') {
  const app = createApp(App)
  app.use(createPinia()).use(buildRouter()).use(buildVuetify())
  app.mount(selector)
  return app
}

mountApp()
