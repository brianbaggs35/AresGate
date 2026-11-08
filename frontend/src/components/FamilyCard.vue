<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { Family } from '@/api/threats'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatCount } from '@/format'
import { OWNER_CALL, reachOf, verdictOf } from '@/threats'
import { CLASSIFICATION } from '@/triage'

/**
 * A kind of incident in a list: what its incidents say, where they come from, how many there are
 * and what is thought of all of them, by you or by the AI. The card is the way to the kind's page.
 */
const props = defineProps<{ family: Family }>()

const reach = computed(() => reachOf(props.family.reach))
const verdict = computed(() => verdictOf(props.family))
const lanes = computed(() =>
  [
    { key: 'threats', count: props.family.threats, label: 'threat' },
    { key: 'suspects', count: props.family.suspects, label: 'suspect' },
    { key: 'background', count: props.family.background, label: 'in the background' },
  ].filter(({ count }) => count > 0),
)
</script>

<template>
  <v-card hover class="family" data-test="family-card">
    <RouterLink
      :to="{ name: 'family', params: { id: family.id } }"
      class="family__link"
      data-test="family"
    >
      <div class="family__top">
        <SeverityChip :severity="family.worst" />
        <v-chip
          v-if="family.owner_call"
          variant="outlined"
          :prepend-icon="OWNER_CALL[family.owner_call].icon"
          data-test="family-owner"
        >
          {{ OWNER_CALL[family.owner_call].label }}
        </v-chip>
        <v-chip
          v-else-if="family.classification"
          variant="outlined"
          :color="CLASSIFICATION[family.classification].color"
          :prepend-icon="CLASSIFICATION[family.classification].icon"
          data-test="family-ai"
        >
          {{ verdict.text }}
        </v-chip>
        <v-chip v-else variant="outlined" data-test="family-waiting">{{ verdict.text }}</v-chip>
        <span class="family__when text-body-medium text-medium-emphasis">
          Last seen
          <time :datetime="family.last_seen_at">{{ formatAgo(family.last_seen_at) }}</time>
        </span>
      </div>
      <h3 class="family__title text-title-large" data-test="family-title">{{ family.label }}</h3>
      <ul class="family__facts text-body-medium text-medium-emphasis">
        <li class="family__fact" data-test="family-reach">
          <v-icon :icon="reach.icon" size="18" aria-hidden="true" />
          {{ reach.label }}
        </li>
        <li class="family__fact" data-test="family-incidents">
          {{ formatCount(family.incidents) }}
          {{ family.incidents === 1 ? 'incident' : 'incidents' }}
          from {{ formatCount(family.actors) }}
          {{ family.actors === 1 ? 'address' : 'addresses' }}
        </li>
        <li class="family__fact" data-test="family-alerts">
          {{ formatCount(family.alerts) }} {{ family.alerts === 1 ? 'alert' : 'alerts' }}
        </li>
        <li class="family__fact">Seen by {{ family.source_name }}</li>
        <li
          v-for="lane in lanes"
          :key="lane.key"
          class="family__fact"
          :data-test="`family-${lane.key}`"
        >
          {{ formatCount(lane.count) }} {{ lane.label }}
        </li>
      </ul>
    </RouterLink>
  </v-card>
</template>

<style scoped>
.family {
  overflow: hidden;
}

.family__link {
  display: block;
  padding: 1rem;
  color: inherit;
  text-decoration: none;
}

@media (min-width: 600px) {
  .family__link {
    padding: 1.25rem;
  }
}

.family__link:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.family__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.family__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.family__when {
  margin-inline-start: auto;
}

.family__title {
  margin: 0.75rem 0;
  overflow-wrap: anywhere;
}

.family__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.family__fact {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
