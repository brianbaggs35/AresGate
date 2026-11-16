<script setup lang="ts">
/**
 * The textures that charts fill their marks with when they are turned on (see `patterns.ts`): one
 * `<pattern>` for each of the eight hues, in the hue's own color with the texture drawn over it
 * in `--chart-ink`. It is mounted once, by the app, so every chart on a page points at the same
 * eight. It has no size and says nothing to a screen reader.
 */
</script>

<template>
  <svg
    class="chart-patterns"
    width="0"
    height="0"
    aria-hidden="true"
    focusable="false"
    data-test="chart-patterns"
  >
    <defs>
      <pattern id="chart-pattern-1" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-1)" />
        <path d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6" stroke="var(--chart-ink)" stroke-width="2" />
      </pattern>
      <pattern id="chart-pattern-2" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-2)" />
        <circle cx="2" cy="2" r="1.4" fill="var(--chart-ink)" />
        <circle cx="6" cy="6" r="1.4" fill="var(--chart-ink)" />
      </pattern>
      <pattern id="chart-pattern-3" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-3)" />
        <path
          d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6 M-2 6 L2 10 M0 0 L8 8 M6 -2 L10 2"
          stroke="var(--chart-ink)"
          stroke-width="1.5"
        />
      </pattern>
      <pattern id="chart-pattern-4" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-4)" />
        <path d="M-2 6 L2 10 M0 0 L8 8 M6 -2 L10 2" stroke="var(--chart-ink)" stroke-width="2" />
      </pattern>
      <pattern id="chart-pattern-5" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-5)" />
        <path d="M0 2 H8 M0 6 H8" stroke="var(--chart-ink)" stroke-width="1.5" />
      </pattern>
      <pattern id="chart-pattern-6" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-6)" />
        <path d="M2 0 V8 M6 0 V8" stroke="var(--chart-ink)" stroke-width="1.5" />
      </pattern>
      <pattern id="chart-pattern-7" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-7)" />
        <circle cx="4" cy="4" r="2" fill="none" stroke="var(--chart-ink)" stroke-width="1.5" />
      </pattern>
      <pattern id="chart-pattern-8" width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--chart-8)" />
        <path d="M4 0 V8 M0 4 H8" stroke="var(--chart-ink)" stroke-width="1" />
      </pattern>
    </defs>
  </svg>
</template>

<style scoped>
.chart-patterns {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
}
</style>
