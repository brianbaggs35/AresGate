<script setup lang="ts">
import { ArrowDownLeft, ArrowUpRight } from '@lucide/vue'

import type { DeviceConnection } from '@/api/devices'
import { DIRECTION } from '@/devices'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { describePort } from '@/ports'

/**
 * What a device did with others over the last week, a row for each peer and port, the most often
 * first: which way it went, the other end (a link to its own page), the port and protocol at the
 * far end, how many times and when last. The direction is said in words, with an arrow beside them.
 */
defineProps<{ connections: readonly DeviceConnection[] }>()
</script>

<template>
  <div class="connections" data-test="connections">
    <table aria-label="Connections">
      <thead class="connections__head text-label-large text-medium-emphasis">
        <tr>
          <th scope="col">Direction</th>
          <th scope="col">Source</th>
          <th scope="col">Destination</th>
          <th scope="col">Port</th>
          <th scope="col" class="connections__right">Seen</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(item, index) in connections"
          :key="index"
          class="connection"
          data-test="connection"
        >
          <td class="connection__direction" data-test="connection-direction">
            <v-icon
              :icon="item.direction === 'outgoing' ? ArrowUpRight : ArrowDownLeft"
              size="16"
              aria-hidden="true"
            />
            {{ DIRECTION[item.direction].label }}
          </td>
          <td class="connection__end" data-label="Source" data-test="connection-source">
            <template v-if="item.direction === 'outgoing'">This device</template>
            <router-link
              v-else-if="item.peer"
              :to="{ name: 'device', params: { address: item.peer } }"
              data-test="connection-peer"
              >{{ item.peer }}</router-link
            >
            <span v-else class="text-medium-emphasis">Unknown address</span>
          </td>
          <td class="connection__end" data-label="Destination" data-test="connection-destination">
            <template v-if="item.direction === 'incoming'">This device</template>
            <router-link
              v-else-if="item.peer"
              :to="{ name: 'device', params: { address: item.peer } }"
              data-test="connection-peer"
              >{{ item.peer }}</router-link
            >
            <span v-else class="text-medium-emphasis">Unknown address</span>
          </td>
          <td class="connection__port" data-label="Port" data-test="connection-port">
            <template v-if="item.port !== null">{{
              describePort(item.port, item.protocol)
            }}</template>
            <template v-else-if="item.protocol">{{ item.protocol }}</template>
            <span v-else class="text-medium-emphasis">Not said</span>
          </td>
          <td class="connection__seen connections__right" data-test="connection-seen">
            {{ formatCount(item.events) }} {{ item.events === 1 ? 'time' : 'times' }},
            <time :datetime="item.last_seen_at" :title="formatDateTime(item.last_seen_at)">{{
              formatAgo(item.last_seen_at)
            }}</time>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.connections {
  container-type: inline-size;
}

table,
tbody {
  display: block;
}

.connections__head {
  display: none;
}

.connection {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem 1rem;
  padding: 0.75rem 0;
}

.connection + .connection {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

th,
td {
  padding: 0;
  text-align: start;
  font-weight: inherit;
}

.connection__direction {
  grid-column: 1 / -1;
  font-weight: 500;
}

.connection__end::before,
.connection__port::before {
  content: attr(data-label);
  display: block;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.connection__end,
.connection__port {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.connection__seen {
  grid-column: 1 / -1;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* A wide card reads as a table: one line to a connection, a heading above the columns. */
@container (min-width: 44rem) {
  .connections__head {
    display: block;
  }

  .connections__head tr,
  .connection {
    display: grid;
    grid-template-columns: 9rem minmax(0, 1fr) minmax(0, 1fr) 9rem 12rem;
    align-items: baseline;
    gap: 1rem;
    padding-block: 0.5rem;
  }

  .connection__direction,
  .connection__seen {
    grid-column: auto;
  }

  .connection__end::before,
  .connection__port::before {
    display: none;
  }

  .connections__right {
    text-align: end;
  }
}
</style>
