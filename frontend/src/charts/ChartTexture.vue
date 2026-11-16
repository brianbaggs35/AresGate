<script setup lang="ts">
import { dashClass, textureClass } from '@/charts/patterns'
import type { LegendItem } from '@/charts/types'

/**
 * A series' texture as a small key, for the legend and the table's headings, drawn over its flat
 * color. It is there all the time and only shows when charts are textured (see
 * `styles/charts.scss`), so it costs nothing otherwise.
 */
defineProps<{
  texture: number
  shape: LegendItem['shape']
  color: string
}>()
</script>

<template>
  <svg
    class="chart-textured chart-texture"
    :class="`chart-texture--${shape}`"
    aria-hidden="true"
    focusable="false"
    data-test="chart-texture"
  >
    <rect
      v-if="shape === 'square'"
      width="100%"
      height="100%"
      rx="2"
      fill="transparent"
      :class="textureClass(texture)"
    />
    <line
      v-else
      x1="1"
      x2="15"
      y1="50%"
      y2="50%"
      stroke-width="3"
      stroke-linecap="round"
      :stroke="color"
      :class="dashClass(texture)"
    />
  </svg>
</template>

<style scoped>
.chart-texture {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* A line's key is drawn dashed in its own color, so the flat bar under it is left out. */
.chart-texture--line {
  background: rgb(var(--v-theme-surface));
}
</style>
