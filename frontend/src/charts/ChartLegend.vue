<script setup lang="ts">
import type { LegendItem } from '@/charts/types'

/**
 * What each color of a chart stands for. Each entry is a switch: turning one off takes that
 * series out of the chart, so the others can be read on their own. One always stays on.
 */
const props = defineProps<{
  items: readonly LegendItem[]
  /** The ids of the series that are turned off. */
  hidden: readonly string[]
}>()
const emit = defineEmits<{ 'update:hidden': [ids: string[]] }>()

function toggle(id: string) {
  const off = props.hidden.includes(id)
  if (!off && props.items.length - props.hidden.length <= 1) return
  emit('update:hidden', off ? props.hidden.filter((other) => other !== id) : [...props.hidden, id])
}
</script>

<template>
  <ul class="chart-legend" aria-label="Series" data-test="chart-legend">
    <li v-for="item in items" :key="item.id">
      <button
        type="button"
        class="chart-legend__item text-body-medium"
        :class="{ 'chart-legend__item--off': hidden.includes(item.id) }"
        :aria-pressed="!hidden.includes(item.id)"
        data-test="chart-legend-item"
        @click="toggle(item.id)"
      >
        <span
          class="chart-legend__key"
          :class="`chart-legend__key--${item.shape}`"
          :style="{ '--key': item.color }"
          aria-hidden="true"
        />
        <v-icon v-if="item.icon" :icon="item.icon" size="16" aria-hidden="true" />
        <span data-test="chart-legend-label">{{ item.label }}</span>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.chart-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 32px;
  padding: 0 0.625rem;
  border: 0;
  border-radius: 8px;
  background: none;
  font-family: inherit;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  cursor: pointer;
}

.chart-legend__item:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.chart-legend__item:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

/* A series that is turned off keeps its place but looks switched off. */
.chart-legend__item--off {
  text-decoration: line-through;
}

.chart-legend__item--off .chart-legend__key {
  opacity: 0.4;
}

.chart-legend__key {
  flex: none;
  background: var(--key);
}

.chart-legend__key--line {
  width: 16px;
  height: 3px;
  border-radius: 2px;
}

.chart-legend__key--square {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

@media (pointer: coarse) {
  .chart-legend__item {
    min-height: 44px;
  }
}
</style>
