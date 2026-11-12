<script setup lang="ts">
import { ListFilter } from '@lucide/vue'
import { computed } from 'vue'

import type { BlockedCounts, DashboardWindow } from '@/api/dashboard'
import SectionCard from '@/components/SectionCard.vue'
import {
  deviceQuery,
  portLabel,
  portQuery,
  reachLabel,
  shareOfSides,
  SIDES,
  sidesSummary,
} from '@/blocked'
import { formatCount } from '@/format'

/**
 * The connections the firewall refused, sorted by the way they were going. Most are the internet
 * knocking and say only that the firewall works; the ones worth knowing are your own devices
 * being turned away, which is what a program that has gone wrong, or a machine that has been
 * taken over and is reaching for its controller, looks like from the firewall. So the card says
 * which is which, which ports the internet tried most and which of your devices were refused most,
 * each with a way to see the log lines.
 */
const props = defineProps<{
  blocked: BlockedCounts
  window: DashboardWindow
  /** The window in words that fit "in ...": "the last 24 hours". */
  lastWords: string
}>()

const summary = computed(() => sidesSummary(props.blocked))
/** The directions that have any blocks, which are the ones the bar draws. */
const shown = computed(() => SIDES.filter((side) => props.blocked[side.key] > 0))
</script>

<template>
  <SectionCard
    title="Which way the blocks went"
    :description="`The connections the firewall refused in ${lastWords}, by where they were going.`"
    class="blocked"
    data-test="blocked-card"
  >
    <p class="blocked__summary text-body-large" data-test="blocked-summary">{{ summary }}</p>

    <div class="blocked__bar" aria-hidden="true" data-test="blocked-bar">
      <span
        v-for="side in shown"
        :key="side.key"
        :style="{
          flexGrow: shareOfSides(blocked, side.key) * 1000,
          background: `rgb(var(--v-theme-${side.color}))`,
        }"
        data-test="blocked-segment"
      />
    </div>

    <dl class="blocked__sides" aria-label="Blocked connections by direction">
      <div
        v-for="side in SIDES"
        :key="side.key"
        class="blocked__side"
        :data-test="`blocked-${side.key}`"
      >
        <dt class="text-body-medium">
          <span
            class="blocked__swatch"
            :style="{ background: `rgb(var(--v-theme-${side.color}))` }"
            aria-hidden="true"
          />
          {{ side.label }}
        </dt>
        <dd class="text-title-large">{{ formatCount(blocked[side.key]) }}</dd>
        <dd class="text-body-small text-medium-emphasis">{{ side.meaning }}</dd>
      </div>
    </dl>

    <div class="blocked__lists">
      <section v-if="blocked.top_devices.length" data-test="blocked-devices">
        <h3 class="text-title-medium">Your devices that were turned away</h3>
        <ol class="blocked__list">
          <li v-for="item in blocked.top_devices" :key="item.address" data-test="blocked-device">
            <span class="blocked__name text-body-large">{{ item.address }}</span>
            <span class="text-body-medium text-medium-emphasis">
              {{ formatCount(item.count) }} {{ item.count === 1 ? 'time' : 'times' }},
              {{ reachLabel(item.destinations) }}
            </span>
            <v-btn
              variant="text"
              size="small"
              :prepend-icon="ListFilter"
              :to="{ name: 'logs', query: { q: deviceQuery(item.address, window) } }"
              :aria-label="`See in logs: blocks from ${item.address}`"
              data-test="blocked-device-logs"
            >
              See in logs
            </v-btn>
          </li>
        </ol>
      </section>

      <section v-if="blocked.top_ports.length" data-test="blocked-ports">
        <h3 class="text-title-medium">Doors the internet tried most</h3>
        <ol class="blocked__list">
          <li v-for="item in blocked.top_ports" :key="item.port" data-test="blocked-port">
            <span class="blocked__name text-body-large">{{ portLabel(item) }}</span>
            <span class="text-body-medium text-medium-emphasis">
              {{ formatCount(item.count) }} {{ item.count === 1 ? 'time' : 'times' }}
            </span>
            <v-btn
              variant="text"
              size="small"
              :prepend-icon="ListFilter"
              :to="{ name: 'logs', query: { q: portQuery(item.port, window) } }"
              :aria-label="`See in logs: blocks to port ${item.port}`"
              data-test="blocked-port-logs"
            >
              See in logs
            </v-btn>
          </li>
        </ol>
      </section>
    </div>
  </SectionCard>
</template>

<style scoped>
.blocked__summary {
  margin: 0 0 1rem;
}

/* The three directions as one bar the width of the card: the figures under it say the same, so it
   is only for the eye. */
.blocked__bar {
  display: flex;
  height: 0.75rem;
  gap: 2px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--v-theme-on-surface), 0.08);
}

.blocked__bar > span {
  flex-basis: 0;
  min-width: 4px;
}

.blocked__sides {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 1rem 1.5rem;
  margin: 1.25rem 0;
}

.blocked__side {
  display: grid;
  gap: 0.125rem;
}

.blocked__side dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.blocked__swatch {
  display: inline-block;
  width: 0.625rem;
  height: 0.625rem;
  margin-inline-end: 0.375rem;
  border-radius: 50%;
}

.blocked__lists {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1.5rem;
}

.blocked__list {
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.blocked__list li {
  display: grid;
  gap: 0.25rem;
  justify-items: start;
  padding: 0.75rem 0;
}

.blocked__list li + li {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.blocked__name {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
