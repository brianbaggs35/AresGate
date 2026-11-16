<script setup lang="ts">
import SparklineChart from '@/charts/SparklineChart.vue'

/**
 * How something has been going, in a small line beside the thing: the shape of it over the last
 * days. It says what it is in words for a screen reader, and shows nothing at all while there is
 * nothing to draw, so a card is not made taller by a flat line that says nothing.
 */
defineProps<{
  /** In order, oldest first. */
  values: readonly number[]
  /** What it shows, in a sentence. */
  label: string
}>()
</script>

<template>
  <div v-if="values.some((value) => value > 0)" class="trend-spark" data-test="trend-spark">
    <SparklineChart :values="values" :label="label" :height="28" />
    <span class="text-body-small text-medium-emphasis" data-test="trend-spark-label">
      {{ label }}
    </span>
  </div>
</template>

<style scoped>
.trend-spark {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-block-start: 0.75rem;
}

.trend-spark > :first-child {
  flex: 0 0 8rem;
  max-inline-size: 40%;
}
</style>
