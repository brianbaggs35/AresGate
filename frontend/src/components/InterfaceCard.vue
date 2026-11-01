<script setup lang="ts">
import { ArrowDown, ArrowUp, Network } from '@lucide/vue'
import { computed } from 'vue'

import type { Interface, Stats } from '@/api/interfaces'
import SparklineChart from '@/charts/SparklineChart.vue'
import { formatAgo, formatBitrate, formatCount } from '@/format'
import { latestSpeed, roleInfo, totalSpeed } from '@/interfaces'

/**
 * One part of the network at a glance: its name and what it is for, how its traffic has gone in
 * the last day, how many alerts came in on it and how many devices live on it, and which programs
 * report about it. The whole card opens the interface.
 */
const props = defineProps<{ item: Interface; stats: Stats | undefined }>()

const role = computed(() => roleInfo(props.item.role))
const programs = computed(() => [...new Set(props.item.feeds.map((feed) => feed.integration_name))])
const trend = computed(() => (props.stats?.speed ? totalSpeed(props.stats.speed) : []))
const received = computed(() =>
  props.stats?.speed ? latestSpeed(props.stats.speed.received) : null,
)
const sent = computed(() => (props.stats?.speed ? latestSpeed(props.stats.speed.sent) : null))

/** How alerts compare with the day before, in words that do not depend on color. */
const alertsNote = computed(() => {
  const stats = props.stats
  if (!stats) return ''
  const change = stats.alerts - stats.alerts_previous
  if (stats.alerts === 0 && stats.alerts_previous === 0) return 'None in two days'
  if (change === 0) return 'Same as the day before'
  return `${change > 0 ? '+' : '−'}${formatCount(Math.abs(change))} since the day before`
})
</script>

<template>
  <v-card
    :to="{ name: 'interface', params: { id: item.id } }"
    class="card"
    data-test="interface-card"
  >
    <div class="card__top">
      <v-chip :prepend-icon="role.icon" size="small" variant="tonal" data-test="interface-role">
        {{ role.label }}
      </v-chip>
      <span v-if="stats?.last_seen_at" class="text-body-small text-medium-emphasis">
        Reported {{ formatAgo(stats.last_seen_at) }}
      </span>
    </div>
    <h3 class="text-title-large card__name" data-test="interface-name">{{ item.name }}</h3>

    <div
      v-if="trend.length && received !== null"
      class="card__traffic"
      data-test="interface-traffic"
    >
      <SparklineChart
        :values="trend"
        :label="`Traffic through ${item.name} in the last 24 hours`"
        :height="40"
      />
      <p class="card__speeds text-body-medium">
        <span class="card__speed" data-test="interface-received">
          <ArrowDown :size="16" aria-hidden="true" />
          <span class="sr-only">Received</span>
          {{ formatBitrate(received) }}
        </span>
        <span v-if="sent !== null" class="card__speed" data-test="interface-sent">
          <ArrowUp :size="16" aria-hidden="true" />
          <span class="sr-only">Sent</span>
          {{ formatBitrate(sent) }}
        </span>
      </p>
    </div>
    <p v-else class="text-body-medium text-medium-emphasis" data-test="interface-no-traffic">
      {{ item.feeds.length ? 'No traffic measured yet.' : 'Nothing is placed here yet.' }}
    </p>

    <dl class="card__facts">
      <div>
        <dt class="text-body-small text-medium-emphasis">Alerts, 24 hours</dt>
        <dd class="text-title-medium" data-test="interface-alerts">
          {{ formatCount(stats?.alerts ?? 0) }}
        </dd>
        <dd class="text-body-small text-medium-emphasis">{{ alertsNote }}</dd>
      </div>
      <div>
        <dt class="text-body-small text-medium-emphasis">Devices</dt>
        <dd class="text-title-medium" data-test="interface-devices">
          {{ stats?.devices === null || stats === undefined ? '–' : formatCount(stats.devices) }}
        </dd>
        <dd v-if="stats && stats.devices === null" class="text-body-small text-medium-emphasis">
          Add its networks to count them
        </dd>
      </div>
    </dl>

    <ul v-if="programs.length" class="card__programs" aria-label="Reported by">
      <li v-for="program in programs" :key="program">
        <v-chip size="x-small" variant="outlined" :prepend-icon="Network">{{ program }}</v-chip>
      </li>
    </ul>
  </v-card>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  height: 100%;
  padding: 1.25rem;
}

.card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.card__name {
  margin: 0;
  overflow-wrap: anywhere;
}

.card__traffic {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.card__speeds {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  margin: 0;
}

.card__speed {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-variant-numeric: tabular-nums;
}

.card__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0;
}

.card__facts dd {
  margin: 0;
}

.card__programs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: auto 0 0;
  padding: 0;
  list-style: none;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
