<script setup lang="ts">
import { TriangleAlert } from '@lucide/vue'

import type { ResponseItem } from '@/api/incidentResponse'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo } from '@/format'
import { answer } from '@/incidentResponse'

/**
 * One incident on the Incident Response page: how serious it is, what it is, and in a line what
 * was done about it, or, for one that needs a response, why. The title leads to the incident,
 * where the decision is made.
 */
defineProps<{ item: ResponseItem }>()
</script>

<template>
  <li class="row" :data-state="item.state" data-test="response-row">
    <div class="row__chips">
      <SeverityChip :severity="item.severity" />
      <IncidentStatusChip :status="item.status" />
    </div>
    <div class="row__main">
      <router-link
        :to="{ name: 'incident', params: { id: item.id } }"
        class="row__title text-title-medium"
        data-test="response-link"
      >
        {{ item.title }}
      </router-link>
      <p v-if="item.why" class="row__line row__line--why text-body-large" data-test="response-why">
        <v-icon :icon="TriangleAlert" color="error" size="18" aria-hidden="true" />
        {{ item.why }}
      </p>
      <p v-else class="row__line text-body-large text-medium-emphasis" data-test="response-answer">
        {{ answer(item) }}
      </p>
    </div>
    <span class="row__when text-body-medium text-medium-emphasis" data-test="response-when">
      {{ formatAgo(item.last_seen_at) }}
    </span>
  </li>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.5rem 1rem;
  padding: 0.875rem 0;
  border-bottom: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
}

.row:last-child {
  border-bottom: 0;
}

.row__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  min-width: 8.5rem;
}

.row__main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.row__title {
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}

.row__title:hover,
.row__title:focus-visible {
  text-decoration: underline;
}

.row__line {
  margin: 0;
}

.row__line--why {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-weight: 500;
}

.row__when {
  white-space: nowrap;
}

/* On a phone the chips and the time sit above the title, so the words have the whole width. */
@media (max-width: 599.98px) {
  .row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .row__chips {
    min-width: 0;
  }

  .row__main {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}
</style>
