<script setup lang="ts">
import { ArrowDown, ArrowUp, Minus } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import SparklineChart from '@/charts/SparklineChart.vue'

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
  /** How it has changed, in words ("+12% since yesterday"). Which way it went is shown by an
   * arrow, and whether that is good or bad by the color, so neither rests on the other. */
  delta?: { text: string; direction: 'up' | 'down' | 'flat'; tone: 'neutral' | 'good' | 'bad' }
  /** How it has been going, oldest first, as a small line beside the number. */
  trend?: readonly (number | null)[]
  /** What the line shows, in words. */
  trendLabel?: string
  to?: RouteLocationRaw
}>()

const COLORS = { neutral: 'primary', good: 'success', warning: 'warning', bad: 'error' } as const
const ARROWS = { up: ArrowUp, down: ArrowDown, flat: Minus } as const
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
    <div class="stat-tile__figures">
      <p class="stat-tile__value text-headline-large" data-test="stat-value">{{ value }}</p>
      <SparklineChart
        v-if="trend?.length"
        class="stat-tile__trend"
        :values="trend"
        :label="trendLabel ?? 'Trend'"
        :color="`rgb(var(--v-theme-${COLORS[props.tone ?? 'neutral']}))`"
      />
    </div>
    <p
      v-if="delta"
      class="stat-tile__delta text-body-medium"
      :class="{ 'text-success': delta.tone === 'good', 'text-error': delta.tone === 'bad' }"
      data-test="stat-delta"
    >
      <v-icon :icon="ARROWS[delta.direction]" size="16" aria-hidden="true" />
      <span>{{ delta.text }}</span>
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

.stat-tile__figures {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.stat-tile__trend {
  flex: 1;
  max-width: 8rem;
  margin-left: auto;
}

.stat-tile__delta {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
</style>
