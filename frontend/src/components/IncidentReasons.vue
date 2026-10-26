<script setup lang="ts">
import { computed } from 'vue'

import type { ConfidenceLevel, Reason } from '@/api/incidents'
import { seriesColor } from '@/charts/palette'
import ConfidenceMeter from '@/components/ConfidenceMeter.vue'
import { reasonLabel } from '@/incidents'

/**
 * Why AresGate is as sure as it is: the reasons, each with the points it adds and what it saw,
 * and a bar that shows how much of the 100 each one is. Nothing is scored that can't be
 * explained here, and the points add up to the number at the top.
 */
const props = defineProps<{
  reasons: readonly Reason[]
  confidence: number
  level: ConfidenceLevel
}>()

const MAXIMUM = 100

const total = computed(() => props.reasons.reduce((sum, { points }) => sum + points, 0))
/** The reasons that add anything, with the share of the bar each takes. A sum over the maximum is
 * cut at it, so the bar never overflows. */
const parts = computed(() => {
  const scale = Math.max(MAXIMUM, total.value)
  return props.reasons.map((reason, index) => ({
    ...reason,
    label: reasonLabel(reason.rule),
    color: seriesColor(index),
    share: (reason.points / scale) * 100,
  }))
})
const capped = computed(() => total.value > MAXIMUM)
</script>

<template>
  <div class="reasons" data-test="reasons">
    <ConfidenceMeter large :bar="false" :confidence="confidence" :level="level" />

    <div class="reasons__bar" aria-hidden="true" data-test="reasons-bar">
      <span
        v-for="part in parts.filter(({ share }) => share > 0)"
        :key="part.rule"
        class="reasons__segment"
        :style="{ width: `${part.share.toString()}%`, background: part.color }"
      />
    </div>

    <ol class="reasons__list">
      <li v-for="part in parts" :key="part.rule" class="reasons__item" data-test="reason">
        <span class="reasons__swatch" :style="{ background: part.color }" aria-hidden="true" />
        <div class="reasons__text">
          <p class="text-title-medium" data-test="reason-label">{{ part.label }}</p>
          <p class="text-body-medium text-medium-emphasis" data-test="reason-text">
            {{ part.text }}
          </p>
        </div>
        <span class="reasons__points text-title-medium tabular-nums" data-test="reason-points">
          +{{ part.points }}
        </span>
      </li>
    </ol>

    <p class="reasons__total text-body-medium text-medium-emphasis" data-test="reasons-total">
      {{ total }} points<template v-if="capped"
        >, counted as {{ MAXIMUM }}, the most there is</template
      >.
    </p>
  </div>
</template>

<style scoped>
.reasons__bar {
  display: flex;
  gap: 2px;
  height: 0.75rem;
  margin: 0.25rem 0 0.5rem;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.reasons__segment {
  display: block;
  height: 100%;
}

.reasons__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.reasons__item {
  display: grid;
  grid-template-columns: 0.75rem minmax(0, 1fr) auto;
  align-items: start;
  gap: 0 0.75rem;
  padding: 0.75rem 0;
}

.reasons__item + .reasons__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.reasons__swatch {
  width: 0.75rem;
  height: 0.75rem;
  margin-top: 0.3rem;
  border-radius: 3px;
}

.reasons__text p {
  margin: 0;
  overflow-wrap: anywhere;
}

.reasons__total {
  margin: 0.25rem 0 0;
}
</style>
