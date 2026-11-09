<script setup lang="ts">
import { ArrowDownLeft, ArrowUpRight } from '@lucide/vue'

import type { AssetEvent } from '@/api/assets'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatDateTime } from '@/format'
import { eventFlow } from '@/inventory'

/**
 * The events one of an asset's addresses was in, newest first: when, how serious, which program
 * reported it and which way it went. The direction is said in words, with an arrow beside them.
 */
defineProps<{ events: readonly AssetEvent[] }>()
</script>

<template>
  <ol class="events" data-test="asset-events-list">
    <li v-for="item in events" :key="item.id" class="event" data-test="asset-event">
      <div class="event__head">
        <time
          class="text-body-medium text-medium-emphasis"
          :datetime="item.occurred_at"
          :title="formatDateTime(item.occurred_at)"
        >
          {{ formatAgo(item.occurred_at) }}
        </time>
        <SeverityChip :severity="item.severity" />
        <span class="text-label-large text-medium-emphasis">{{ item.source_name }}</span>
      </div>
      <p class="text-body-large event__summary">{{ item.summary }}</p>
      <p class="text-body-medium text-medium-emphasis event__flow" data-test="asset-event-flow">
        <v-icon :icon="item.outbound ? ArrowUpRight : ArrowDownLeft" size="16" aria-hidden="true" />
        {{ eventFlow(item) }}
        <template v-if="item.signature">· {{ item.signature }}</template>
      </p>
    </li>
  </ol>
</template>

<style scoped>
.events {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.event {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 0;
}

.event + .event {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.event__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.event__summary,
.event__flow {
  margin: 0;
  overflow-wrap: anywhere;
}

.event__flow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
}
</style>
