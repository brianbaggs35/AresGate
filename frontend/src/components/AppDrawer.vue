<script setup lang="ts">
import { ChevronsLeft, ChevronsRight } from '@lucide/vue'
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

import AppLogo from '@/components/AppLogo.vue'
import { navItems } from '@/navigation'
import { useNavigationStore } from '@/stores/navigation'

const display = useDisplay()
const store = useNavigationStore()

// A tablet starts with just the icons, to leave the page room. Whatever a person picks after
// that is remembered, and applies on every screen.
const rail = computed(() => (store.width ? store.width === 'rail' : display.sm.value))
</script>

<template>
  <v-navigation-drawer
    permanent
    :rail="rail"
    :width="264"
    :rail-width="72"
    border="e"
    aria-label="Main"
    class="app-drawer"
  >
    <div class="app-drawer__brand">
      <router-link to="/" class="text-decoration-none text-high-emphasis" aria-label="AresGate">
        <AppLogo :compact="rail" />
      </router-link>
    </div>

    <!-- The list's own role (list) wants list items, and these are links, so it steps aside. -->
    <v-list nav role="presentation" tabindex="-1" class="px-3">
      <v-list-item
        v-for="item in navItems"
        :key="item.route"
        :to="{ name: item.route }"
        :prepend-icon="item.icon"
        :title="item.title"
        rounded="lg"
        color="primary"
        :tabindex="0"
        :data-test="`nav-${item.route}`"
      >
        <!-- The link's name is already its title, so a tooltip would only say it twice. -->
        <v-tooltip
          v-if="rail"
          activator="parent"
          location="end"
          :text="item.title"
          aria-hidden="true"
          data-test="menu-tooltip"
        />
      </v-list-item>
    </v-list>

    <template #append>
      <div class="app-drawer__footer">
        <v-btn
          :icon="rail ? ChevronsRight : ChevronsLeft"
          variant="text"
          size="small"
          :aria-label="rail ? 'Expand the menu' : 'Collapse the menu'"
          :aria-expanded="!rail"
          data-test="menu-width"
          @click="store.setWidth(rail ? 'full' : 'rail')"
        />
      </div>
    </template>
  </v-navigation-drawer>
</template>
