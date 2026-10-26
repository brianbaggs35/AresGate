<script setup lang="ts">
import type { ConfidenceLevel } from '@/api/incidents'
import { CONFIDENCE } from '@/incidents'

/**
 * How sure AresGate is that something is a real attack: a word, a bar and the number it comes
 * from out of 100, so the bar never has to be read alone. It is one hue, because how sure it is
 * isn't how serious it is, which has its own colors and icons.
 */
withDefaults(
  defineProps<{
    confidence: number
    level: ConfidenceLevel
    /** For the top of a page, where it is the answer to the question being asked. */
    large?: boolean
    /** Whether to draw the bar, which a parent that draws its own leaves out. */
    bar?: boolean
  }>(),
  { large: false, bar: true },
)
</script>

<template>
  <div class="confidence" data-test="confidence">
    <div class="confidence__text">
      <span
        :class="large ? 'text-title-large' : 'text-label-large'"
        :data-level="level"
        data-test="confidence-level"
      >
        {{ CONFIDENCE[level] }} confidence
      </span>
      <span class="text-body-medium text-medium-emphasis tabular-nums" data-test="confidence-value">
        {{ confidence }} of 100
      </span>
    </div>
    <v-progress-linear
      v-if="bar"
      :model-value="confidence"
      color="primary"
      :height="large ? 12 : 6"
      rounded
      :aria-label="`Confidence ${confidence.toString()} out of 100`"
    />
  </div>
</template>

<style scoped>
.confidence__text {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0 0.75rem;
  margin-bottom: 0.375rem;
}
</style>
