<script setup lang="ts">
import { computed } from 'vue'

import { formatBytes } from '@/format'

/** How much of something is used: a bar, and the figures in words so they don't rest on colour. */
const props = defineProps<{
  label: string
  used: number
  total: number
}>()

/** From this share of the whole the bar warns, and from the second it says it is nearly gone. */
const WARN = 75
const CRITICAL = 90

const share = computed(() =>
  props.total > 0 ? Math.min(100, Math.round((props.used / props.total) * 100)) : 0,
)
const color = computed(() => {
  if (share.value >= CRITICAL) return 'error'
  if (share.value >= WARN) return 'warning'
  return 'primary'
})
</script>

<template>
  <div class="usage-meter" data-test="usage-meter">
    <div class="usage-meter__text">
      <span class="text-body-large" data-test="usage-label">{{ label }}</span>
      <span class="text-body-medium text-medium-emphasis tabular-nums" data-test="usage-figures">
        {{ formatBytes(used) }} of {{ formatBytes(total) }} · {{ share }}%
      </span>
    </div>
    <v-progress-linear
      :model-value="share"
      :color="color"
      :aria-label="`${label} in use`"
      height="8"
      rounded
    />
  </div>
</template>

<style scoped>
.usage-meter__text {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  margin-bottom: 0.5rem;
}
</style>
