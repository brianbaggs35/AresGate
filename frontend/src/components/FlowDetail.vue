<script setup lang="ts">
import { ScrollText, X } from '@lucide/vue'
import { computed } from 'vue'

import type { Flow, FlowHours, FlowNode } from '@/api/flow'
import { formatCount } from '@/format'
import { COLUMN_TITLES, isOthers, logSearch, neighbours, nodeLabel, refusedShare } from '@/flow'

/**
 * What the block that was picked in the picture is: how many connections went through it and how
 * many of those the firewall refused, what it is joined to, and where to read more, which is the
 * Logs with the search that finds just these connections, and for an address its page in Devices.
 */
const props = defineProps<{ flow: Flow; node: FlowNode; hours: FlowHours }>()
const emit = defineEmits<{ close: [] }>()

const joined = computed(() => neighbours(props.node.id, props.flow))
const search = computed(() => logSearch(props.node, props.hours))
const share = computed(() => refusedShare(props.node.events, props.node.blocked))
/** Whether it is an address, which has a page in Devices. */
const address = computed(() => props.node.column !== 'service' && !isOthers(props.node))
/** What went from one block to the next: how many, and of them how many were refused. */
const amount = (item: { events: number; blocked: number }) =>
  item.blocked > 0
    ? `${formatCount(item.events)}, ${formatCount(item.blocked)} refused`
    : formatCount(item.events)
const sideTitle = computed(() => (props.node.column === 'service' ? 'Used by' : 'Connected'))
</script>

<template>
  <aside class="detail" aria-labelledby="flow-detail-title" data-test="flow-detail">
    <div class="detail__head">
      <div class="detail__titles">
        <p class="text-label-large text-medium-emphasis">{{ COLUMN_TITLES[node.column] }}</p>
        <h2 id="flow-detail-title" class="text-title-large detail__name" data-test="detail-name">
          {{ nodeLabel(node) }}
        </h2>
        <p v-if="node.name" class="text-body-medium text-medium-emphasis" data-test="detail-host">
          {{ node.name }}
        </p>
      </div>
      <v-btn
        :icon="X"
        variant="text"
        size="small"
        aria-label="Close the details"
        data-test="detail-close"
        @click="emit('close')"
      />
    </div>

    <dl class="detail__facts">
      <div>
        <dt class="text-label-large text-medium-emphasis">Connections</dt>
        <dd class="text-title-medium tabular-nums" data-test="detail-events">
          {{ formatCount(node.events) }}
        </dd>
      </div>
      <div>
        <dt class="text-label-large text-medium-emphasis">Refused</dt>
        <dd class="text-title-medium tabular-nums" data-test="detail-blocked">
          {{ formatCount(node.blocked) }}
          <span class="text-body-medium text-medium-emphasis">({{ share }}%)</span>
        </dd>
      </div>
      <div v-if="node.scope">
        <dt class="text-label-large text-medium-emphasis">Where</dt>
        <dd class="text-title-medium" data-test="detail-scope">
          {{ node.scope === 'outside' ? 'On the Internet' : 'On your network' }}
        </dd>
      </div>
    </dl>

    <section v-if="joined.length" aria-labelledby="flow-detail-joined">
      <h3 id="flow-detail-joined" class="text-title-small">{{ sideTitle }}</h3>
      <ul class="detail__list" data-test="detail-joined">
        <li v-for="item in joined" :key="item.node.id" class="detail__item">
          <span class="detail__who">{{ nodeLabel(item.node) }}</span>
          <span class="tabular-nums text-medium-emphasis">{{ amount(item) }}</span>
        </li>
      </ul>
    </section>

    <div class="detail__actions">
      <v-btn
        v-if="search"
        variant="tonal"
        color="primary"
        :prepend-icon="ScrollText"
        :to="{ name: 'logs', query: { q: search } }"
        data-test="detail-logs"
      >
        Read these in the logs
      </v-btn>
      <v-btn
        v-if="address"
        variant="text"
        :to="{ name: 'device', params: { address: node.label } }"
        data-test="detail-device"
      >
        Open the device
      </v-btn>
    </div>
  </aside>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.detail__titles p,
.detail__name {
  margin: 0;
}

.detail__name {
  overflow-wrap: anywhere;
}

.detail__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 2rem;
  margin: 0;
}

.detail__facts dd {
  margin: 0;
}

.detail__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.detail__item {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding-block: 0.25rem;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.detail__who {
  overflow-wrap: anywhere;
}

.detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
