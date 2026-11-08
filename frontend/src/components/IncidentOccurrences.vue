<script setup lang="ts">
import { Copy } from '@lucide/vue'
import { computed } from 'vue'

import type { Occurrence } from '@/api/incidents'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatCount } from '@/format'

/**
 * The alerts of an incident that happened again and again, as one line each with how many times:
 * a scanner that sent the same probe four hundred times is one alert that happened four hundred
 * times, and not four hundred alerts. Where another program had already reported one, it counts
 * once, and the line says so.
 */
const props = defineProps<{ occurrences: readonly Occurrence[] }>()

/** Only those that happened more than once or were reported by two programs. */
const repeated = computed(() =>
  props.occurrences.filter(({ count, duplicates }) => count > 1 || duplicates > 0),
)
const MOST = 8
const shown = computed(() => repeated.value.slice(0, MOST))
</script>

<template>
  <ul class="occurrences" data-test="occurrences">
    <li
      v-for="(item, index) in shown"
      :key="index"
      class="occurrences__item"
      data-test="occurrence"
    >
      <SeverityChip :severity="item.signal.severity" />
      <div class="occurrences__text">
        <p class="text-body-large" data-test="occurrence-summary">{{ item.signal.summary }}</p>
        <p class="text-body-medium text-medium-emphasis">
          <b class="tabular-nums" data-test="occurrence-count">{{ formatCount(item.count) }}</b>
          {{ item.count === 1 ? 'time' : 'times' }} from {{ item.signal.source_name }}, the last
          <time :datetime="item.last_at">{{ formatAgo(item.last_at) }}</time
          >.
          <span v-if="item.duplicates > 0" data-test="occurrence-duplicates">
            <v-icon :icon="Copy" size="16" aria-hidden="true" />
            {{ formatCount(item.duplicates) }} also reported by another program, counted once.
          </span>
        </p>
      </div>
    </li>
    <li
      v-if="repeated.length > shown.length"
      class="text-body-medium text-medium-emphasis"
      data-test="occurrences-more"
    >
      And {{ formatCount(repeated.length - shown.length) }} more that repeated.
    </li>
  </ul>
</template>

<style scoped>
.occurrences {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.occurrences__item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.occurrences__text p {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
