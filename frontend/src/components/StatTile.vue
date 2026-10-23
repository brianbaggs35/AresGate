<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

/**
 * One number that matters, with its name and a line of context: the building block of the
 * dashboard and of the top of every list. With `to` the whole tile leads to where the number
 * comes from.
 */
const props = defineProps<{
  label: string
  value: string | number
  /** What the number is measured against or when it was taken, such as "last 24 hours". */
  hint?: string
  icon?: NonNullable<IconProps['icon']>
  /** How the number is doing, which also colors its icon. */
  tone?: 'neutral' | 'good' | 'warning' | 'bad'
  to?: RouteLocationRaw
}>()

const COLORS = { neutral: 'primary', good: 'success', warning: 'warning', bad: 'error' } as const
</script>

<template>
  <v-card :to="to" :hover="to !== undefined" class="stat-tile pa-5" data-test="stat-tile">
    <div class="stat-tile__label text-label-large text-medium-emphasis">
      <v-icon
        v-if="icon"
        :icon="icon"
        :color="COLORS[props.tone ?? 'neutral']"
        size="20"
        aria-hidden="true"
      />
      <span data-test="stat-label">{{ label }}</span>
    </div>
    <p class="stat-tile__value text-headline-large tabular-nums" data-test="stat-value">
      {{ value }}
    </p>
    <p v-if="hint" class="text-body-medium text-medium-emphasis" data-test="stat-hint">
      {{ hint }}
    </p>
  </v-card>
</template>

<style scoped>
.stat-tile {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  height: 100%;
  text-decoration: none;
}

.stat-tile__label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stat-tile p {
  margin: 0;
}
</style>
