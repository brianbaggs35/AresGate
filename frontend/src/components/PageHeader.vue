<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'

/**
 * The top of a page: its title, what it is for, and the actions that belong to the whole page.
 * A page that sits under another has a way back to it above the title.
 */
defineProps<{
  title: string
  description?: string
  /** Where the way back leads, and what it is called. */
  back?: { to: RouteLocationRaw; label: string }
}>()
</script>

<template>
  <header class="page-header">
    <v-btn
      v-if="back"
      variant="text"
      :prepend-icon="ArrowLeft"
      :to="back.to"
      class="page-header__back"
      data-test="back"
    >
      {{ back.label }}
    </v-btn>
    <div class="page-header__row">
      <span v-if="$slots.icon" class="page-header__icon" aria-hidden="true">
        <slot name="icon" />
      </span>
      <div class="page-header__text">
        <div class="page-header__title">
          <h1 class="text-headline-medium" data-test="page-heading">{{ title }}</h1>
          <slot name="badge" />
        </div>
        <p
          v-if="description"
          class="text-body-large text-medium-emphasis"
          data-test="page-description"
        >
          {{ description }}
        </p>
        <slot />
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<style scoped>
.page-header__back {
  margin-left: -0.75rem;
  margin-bottom: 0.5rem;
}

.page-header__row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.75rem 1rem;
}

.page-header__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 3.75rem;
  height: 3.75rem;
  border-radius: 16px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.page-header__text {
  flex: 1 1 18rem;
  min-width: 0;
}

.page-header__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.page-header__title h1 {
  margin: 0;
}

.page-header__text p,
.page-header__text :slotted(p) {
  margin: 0.25rem 0 0;
}

.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
