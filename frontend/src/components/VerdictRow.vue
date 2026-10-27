<script setup lang="ts">
import { Pencil, Undo2 } from '@lucide/vue'
import { computed } from 'vue'

import type { Verdict } from '@/api/verdicts'
import VerdictChip from '@/components/VerdictChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { aboutVerdict } from '@/verdicts'

/**
 * One verdict in the list of them: what it says, what it is about, why, how often it has been
 * used and when it was given, with the means to change it or take it back.
 */
const props = defineProps<{ rule: Verdict }>()
const emit = defineEmits<{ change: []; remove: [] }>()

const about = computed(() => aboutVerdict(props.rule))
const used = computed(() => {
  const { hits, last_hit_at: last } = props.rule
  if (hits === 0 || last === null) return 'Not applied to a signal yet'
  const signals = `${formatCount(hits)} ${hits === 1 ? 'signal' : 'signals'}`
  return `Applied to ${signals}, the last ${formatAgo(last)}`
})
</script>

<template>
  <li class="verdict-row" data-test="verdict-row">
    <div class="verdict-row__body">
      <div class="verdict-row__what">
        <VerdictChip :verdict="rule.verdict" />
        <span class="verdict-row__about text-title-medium" data-test="verdict-about">{{
          about
        }}</span>
      </div>
      <p v-if="rule.note" class="text-body-large" data-test="verdict-why">Why: {{ rule.note }}</p>
      <p class="text-body-medium text-medium-emphasis" data-test="verdict-meta">
        {{ used }} ·
        <time :datetime="rule.created_at">Given {{ formatDateTime(rule.created_at) }}</time>
      </p>
    </div>
    <div class="verdict-row__actions">
      <v-btn
        variant="outlined"
        :prepend-icon="Pencil"
        data-test="verdict-change"
        @click="emit('change')"
      >
        Change
      </v-btn>
      <v-btn
        variant="text"
        :prepend-icon="Undo2"
        data-test="verdict-remove"
        @click="emit('remove')"
      >
        Take back
      </v-btn>
    </div>
  </li>
</template>

<style scoped>
.verdict-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1.5rem;
  padding: 1rem 0;
}

.verdict-row + .verdict-row {
  border-block-start: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.verdict-row__body {
  flex: 1 1 20rem;
  min-width: 0;
}

.verdict-row__body p {
  margin: 0.25rem 0 0;
  overflow-wrap: anywhere;
}

.verdict-row__what {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem 0.75rem;
}

.verdict-row__about {
  min-width: 0;
  overflow-wrap: anywhere;
}

.verdict-row__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
