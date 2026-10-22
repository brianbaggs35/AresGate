import { mount, type ComponentMountingOptions } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, type Component } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { VApp } from 'vuetify/components'

import { buildVuetify } from '@/plugins/vuetify'
import { buildRouter } from '@/router'
import { useSessionStore } from '@/stores/session'
import { track } from '@/test/cleanup'

export interface MountOptions {
  route?: string
  props?: Record<string, unknown>
  slots?: ComponentMountingOptions<Component>['slots']
  /** Wrap in <v-app>, which layout components such as drawers and app bars require. */
  withApp?: boolean
  /** Viewport width used for Vuetify's display breakpoints (jsdom defaults to 1024, i.e. mobile). */
  width?: number
  /** Starts signed in as this user, so a page or the app's frame has someone to show. */
  signedIn?: string
  /** Runs after Pinia is active and before mounting, e.g. to seed stores. */
  beforeMount?: () => void
}

export async function mountWithPlugins(component: Component, options: MountOptions = {}) {
  if (options.width) window.innerWidth = options.width
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = buildRouter(createMemoryHistory())
  const vuetify = buildVuetify()
  if (options.signedIn) {
    useSessionStore().$patch({
      known: true,
      username: options.signedIn,
      csrfToken: 'a-security-token',
    })
  }
  options.beforeMount?.()

  if (options.route) {
    await router.push(options.route)
    await router.isReady()
  }

  const root = options.withApp
    ? defineComponent({
        render: () => h(VApp, () => h(component, options.props, options.slots as never)),
      })
    : component

  const wrapper = mount(root, {
    props: options.withApp ? undefined : options.props,
    slots: options.withApp ? undefined : options.slots,
    global: { plugins: [pinia, router, vuetify] },
    attachTo: document.body,
  })
  track(wrapper)
  await router.isReady()
  return { wrapper, router, pinia, vuetify }
}

export function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve))
}
