<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

import AppLogo from '@/components/AppLogo.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import UserMenu from '@/components/UserMenu.vue'
import { shortcutLabel } from '@/commands'
import { pageTitle } from '@/router'
import { usePaletteStore } from '@/stores/palette'

const route = useRoute()
const display = useDisplay()
const palette = usePaletteStore()

const title = computed(() => pageTitle(route))
const shortcut = shortcutLabel(navigator.userAgent)
</script>

<template>
  <v-app-bar flat border="b">
    <!-- The menu has the logo, except on a phone, whose menu is a bar at the bottom. -->
    <v-app-bar-title v-if="display.xs.value">
      <router-link to="/" class="text-decoration-none text-high-emphasis" aria-label="AresGate">
        <AppLogo />
      </router-link>
    </v-app-bar-title>
    <v-app-bar-title v-else class="px-2" data-test="page-title">{{ title }}</v-app-bar-title>
    <template #append>
      <!-- A phone has no Ctrl and K, so the button is how it gets to the palette. -->
      <v-btn
        v-if="display.xs.value"
        :icon="Search"
        variant="text"
        aria-label="Search"
        data-test="palette-open"
        @click="palette.toggle()"
      />
      <v-btn
        v-else
        variant="outlined"
        :prepend-icon="Search"
        aria-keyshortcuts="Control+K Meta+K"
        class="app-bar__search"
        data-test="palette-open"
        @click="palette.toggle()"
      >
        Search
        <kbd class="app-bar__key">{{ shortcut }}</kbd>
      </v-btn>
      <ThemeToggle />
      <UserMenu />
    </template>
  </v-app-bar>
</template>

<style scoped>
.app-bar__search {
  margin-inline-end: 0.5rem;
  text-transform: none;
  letter-spacing: normal;
}

/* The shortcut sits in the button like a key cap, so it reads as a hint and not as a label. */
.app-bar__key {
  margin-inline-start: 0.75rem;
  padding: 0.0625rem 0.375rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  font: inherit;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
</style>
