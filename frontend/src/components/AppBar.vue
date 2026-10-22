<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

import AppLogo from '@/components/AppLogo.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { pageTitle } from '@/router'

const route = useRoute()
const display = useDisplay()

const title = computed(() => pageTitle(route))
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
      <ThemeToggle />
    </template>
  </v-app-bar>
</template>
