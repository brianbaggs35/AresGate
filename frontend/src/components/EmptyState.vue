<script setup lang="ts">
import type { IconProps } from 'vuetify'

/**
 * What a list or panel shows when there is nothing in it yet, or nothing that matches: what is
 * missing and what to do about it (the actions go in the slot).
 */
defineProps<{
  title: string
  description?: string
  icon?: NonNullable<IconProps['icon']>
}>()
</script>

<template>
  <div class="empty-state">
    <v-icon v-if="icon" :icon="icon" size="40" class="empty-state__icon" aria-hidden="true" />
    <p class="text-title-medium" data-test="empty-title">{{ title }}</p>
    <p v-if="description" class="text-body-medium text-medium-emphasis" data-test="empty-text">
      {{ description }}
    </p>
    <div v-if="$slots.default" class="empty-state__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
  text-align: center;
}

.empty-state p {
  margin: 0;
  max-width: 34rem;
}

.empty-state__icon {
  color: rgb(var(--v-theme-primary));
  opacity: 0.8;
}

.empty-state__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}
</style>
