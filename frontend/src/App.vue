<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'
import { watch } from 'vue'
import { useTheme } from 'vuetify'

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
        <span class="d-inline-flex align-center ga-2">
          <v-icon :icon="ShieldCheck" color="primary" />
          <span class="font-weight-bold">AresGate</span>
        </span>
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
