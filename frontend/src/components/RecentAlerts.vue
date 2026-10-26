<script setup lang="ts">
import type { DashboardAlert } from '@/api/dashboard'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatDateTime } from '@/format'

/** The latest alerts, the newest first: how serious each is, what it says, who reported it and
 * when, and the addresses it names. */
defineProps<{ alerts: readonly DashboardAlert[] }>()
</script>

<template>
  <ul class="recent-alerts" data-test="recent-alerts">
    <li
      v-for="alert in alerts"
      :key="alert.id"
      class="recent-alerts__item"
      data-test="recent-alert"
    >
      <div class="recent-alerts__severity">
        <SeverityChip :severity="alert.severity" />
      </div>
      <div class="recent-alerts__text">
        <div class="text-body-large" data-test="alert-summary">{{ alert.summary }}</div>
        <div class="text-body-medium text-medium-emphasis" data-test="alert-detail">
          {{ alert.source_name }} ·
          <time :datetime="alert.occurred_at" :title="formatDateTime(alert.occurred_at)">{{
            formatAgo(alert.occurred_at)
          }}</time>
          <template v-if="alert.src_address">
            · {{ alert.src_address
            }}<template v-if="alert.dst_address"> → {{ alert.dst_address }}</template>
          </template>
        </div>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.recent-alerts {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-alerts__item {
  display: grid;
  grid-template-columns: 6.5rem minmax(0, 1fr);
  align-items: start;
  gap: 0.25rem 0.75rem;
  padding: 0.75rem 0;
}

.recent-alerts__item + .recent-alerts__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.recent-alerts__text {
  min-width: 0;
  overflow-wrap: anywhere;
}

/* On a phone the chip sits above the words, so they get the whole width. */
@media (max-width: 599px) {
  .recent-alerts__item {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
