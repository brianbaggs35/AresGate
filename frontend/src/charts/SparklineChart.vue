<script setup lang="ts">
import { computed } from 'vue'

import { linePath, type Point } from '@/charts/paths'
import { linear } from '@/charts/scales'

/**
 * A small line of how something has been going, with no axes: only its shape and where it is now.
 * It runs from its own lowest to its own highest, so it says which way things are heading and
 * nothing about how much; the number beside it says that. The line is quiet and the latest
 * reading wears the color.
 */
const props = withDefaults(
  defineProps<{
    /** In order, oldest first; null where nothing was measured. */
    values: readonly (number | null)[]
    /** What it shows and where it ended, in words, because the line alone says neither. */
    label: string
    color?: string
    height?: number
  }>(),
  { color: 'var(--chart-1)', height: 32 },
)

/** The room above and below, so the line and its dot are never cut off. */
const PADDING = 6
const WIDTH = 100

const known = computed(() => props.values.filter((value): value is number => value !== null))
const place = computed(() => {
  const low = Math.min(...known.value)
  const high = Math.max(...known.value)
  return linear([low, high], [props.height - PADDING, PADDING])
})
const across = (index: number) =>
  props.values.length > 1 ? (index / (props.values.length - 1)) * WIDTH : WIDTH / 2

const path = computed(() =>
  linePath(
    props.values.map<Point>((value, index) => [
      across(index),
      value === null ? null : place.value(value),
    ]),
  ),
)
const latest = computed(() => {
  let index = props.values.length - 1
  while (index >= 0 && props.values[index] === null) index--
  return index < 0 ? null : { index, value: props.values[index] as number }
})
</script>

<template>
  <div class="sparkline" :style="{ height: `${height}px` }" role="img" :aria-label="label">
    <svg
      v-if="known.length"
      :viewBox="`0 0 ${WIDTH} ${height}`"
      preserveAspectRatio="none"
      aria-hidden="true"
      data-test="sparkline"
    >
      <path
        :d="path"
        class="sparkline__line"
        fill="none"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <!-- Not part of the drawing, which is stretched to the width: a dot there would be an oval. -->
    <span
      v-if="latest"
      class="sparkline__dot"
      :style="{
        left: `${across(latest.index)}%`,
        top: `${place(latest.value)}px`,
        background: color,
      }"
      data-test="sparkline-dot"
    />
  </div>
</template>

<style scoped>
.sparkline {
  position: relative;
  min-width: 4rem;
  /* Room for the dot at either end, which is wider than the line. */
  margin-inline: 5px;
}

.sparkline svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.sparkline__line {
  stroke: var(--chart-other);
}

.sparkline__dot {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgb(var(--v-theme-surface));
  transform: translate(-50%, -50%);
}
</style>
