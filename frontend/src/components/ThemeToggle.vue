<script setup lang="ts">
import { Monitor, Moon, Sun } from '@lucide/vue'
import { computed } from 'vue'

import { useThemeStore, type ThemePreference } from '@/stores/theme'

const store = useThemeStore()

const optionsByValue = {
  light: { value: 'light', title: 'Light', icon: Sun },
  dark: { value: 'dark', title: 'Dark', icon: Moon },
  system: { value: 'system', title: 'System', icon: Monitor },
} as const satisfies Record<
  ThemePreference,
  { value: ThemePreference; title: string; icon: unknown }
>

const options = Object.values(optionsByValue)
const current = computed(() => optionsByValue[store.preference])
</script>

<template>
  <v-menu location="bottom end">
    <template #activator="{ props: activator }">
      <v-btn
        v-bind="activator"
        :icon="current.icon"
        variant="text"
        :aria-label="`Theme: ${current.title}`"
        data-test="theme-toggle"
      />
    </template>
    <v-list density="compact" min-width="160">
      <v-list-item
        v-for="option in options"
        :key="option.value"
        :prepend-icon="option.icon"
        :title="option.title"
        :active="option.value === store.preference"
        color="primary"
        :data-test="`theme-${option.value}`"
        @click="store.setPreference(option.value)"
      />
    </v-list>
  </v-menu>
</template>
