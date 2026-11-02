<script setup lang="ts">
import { ListFilter } from '@lucide/vue'
import { computed } from 'vue'

import type { Attention } from '@/api/dashboard'
import { filteredOut } from '@/dashboard'
import { formatCount } from '@/format'

/**
 * What the dashboard left out, under the status hero: of the incidents going on in the window,
 * how many need you and how many were filtered out, and why, each reason a link to the incidents
 * it hid. What is left out is never hidden for good: a headline that counts only what survives
 * the filters is believable only while the rest is one click away.
 */
const props = defineProps<{
  attention: Attention
  /** When the window began, for the links to search by. */
  since: string
  /** The window in words that fit "in ...": "the last 24 hours". */
  lastWords: string
}>()

const reasons = computed(() => filteredOut(props.attention, props.since))
const filtered = computed(() => reasons.value.reduce((sum, { count }) => sum + count, 0))
const noun = (count: number) => (count === 1 ? 'incident' : 'incidents')
</script>

<template>
  <section class="filtered" aria-labelledby="filtered-title" data-test="filtered">
    <h2 id="filtered-title" class="filtered__title text-title-medium">
      <ListFilter :size="20" aria-hidden="true" />
      <span data-test="filtered-summary">
        {{ formatCount(attention.incidents) }} {{ noun(attention.incidents) }} in {{ lastWords }}:
        {{ formatCount(attention.needs_you) }}
        {{ attention.needs_you === 1 ? 'needs' : 'need' }} you, {{ formatCount(filtered) }} filtered
        out.
      </span>
    </h2>
    <div class="filtered__row">
      <ul v-if="reasons.length" class="filtered__reasons" aria-label="Why they were filtered out">
        <li v-for="reason in reasons" :key="reason.key">
          <v-chip
            variant="outlined"
            :to="reason.to"
            :data-test="`filtered-${reason.key}`"
            :aria-label="`${formatCount(reason.count)} ${reason.label}: see them`"
          >
            {{ formatCount(reason.count) }} {{ reason.label }}
          </v-chip>
        </li>
      </ul>
      <v-btn
        variant="text"
        size="small"
        :to="{ name: 'settings-noise-filters' }"
        data-test="filtered-settings"
      >
        Change what is filtered
      </v-btn>
    </div>
  </section>
</template>

<style scoped>
.filtered {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.filtered__title {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
  font-weight: 500;
}

.filtered__title > svg {
  flex: none;
  margin-top: 0.15rem;
}

.filtered__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.filtered__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
