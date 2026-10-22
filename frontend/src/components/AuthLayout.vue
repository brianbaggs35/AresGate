<script setup lang="ts">
import AppLogo from '@/components/AppLogo.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'

defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <v-container class="auth-layout" max-width="480">
    <div class="d-flex align-center justify-space-between mb-6">
      <AppLogo />
      <ThemeToggle />
    </div>
    <v-card class="pa-6 pa-sm-8" data-test="auth-card">
      <h1 class="text-headline-small mb-1" data-test="auth-title">{{ title }}</h1>
      <p v-if="subtitle" class="text-body-medium text-medium-emphasis mb-6">{{ subtitle }}</p>
      <slot />
    </v-card>
  </v-container>
</template>

<style scoped>
/* Centred in the window, unless the card is taller than it. */
.auth-layout {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 100%;
}
</style>
