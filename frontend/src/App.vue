<script setup lang="ts">
import { watch } from 'vue'
import { useTheme } from 'vuetify'

import AppLogo from '@/components/AppLogo.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useThemeStore } from '@/stores/theme'

const theme = useTheme()
const themeStore = useThemeStore()

watch(
  () => themeStore.preference,
  (preference) => theme.change(preference),
  { immediate: true },
)
</script>

<template>
  <v-app>
    <v-app-bar flat border="b">
      <v-app-bar-title>
        <router-link to="/" class="text-decoration-none text-high-emphasis" aria-label="AresGate">
          <AppLogo />
        </router-link>
      </v-app-bar-title>
      <template #append>
        <ThemeToggle />
      </template>
    </v-app-bar>
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
