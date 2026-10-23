<script setup lang="ts">
import { useDisplay } from 'vuetify'

import type { SettingsSection } from '@/settings'

/**
 * The Settings area's pages: a list beside the page on a computer, and tabs above it on a phone
 * or tablet. Both are links, so each page has an address of its own.
 */
defineProps<{ sections: readonly SettingsSection[] }>()

const display = useDisplay()
</script>

<template>
  <nav aria-label="Settings" class="settings-nav" data-test="settings-nav">
    <v-tabs v-if="display.smAndDown.value" show-arrows color="primary" density="comfortable">
      <v-tab
        v-for="section in sections"
        :key="section.route"
        :to="{ name: section.route }"
        :prepend-icon="section.icon"
        :text="section.title"
        :data-test="`settings-nav-${section.key}`"
      />
    </v-tabs>
    <!-- The list's own role (list) wants list items, and these are links, so it steps aside. -->
    <v-list v-else nav role="presentation" tabindex="-1" class="pa-0">
      <v-list-item
        v-for="section in sections"
        :key="section.route"
        :to="{ name: section.route }"
        :prepend-icon="section.icon"
        :title="section.title"
        rounded="lg"
        color="primary"
        :tabindex="0"
        :data-test="`settings-nav-${section.key}`"
      />
    </v-list>
  </nav>
</template>
