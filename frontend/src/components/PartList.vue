<script setup lang="ts">
import { ChevronRight, CircleAlert, CircleCheck, CircleDashed, Unplug } from '@lucide/vue'

import type { Part, PartState } from '@/api/status'
import { formatAgo } from '@/format'

/**
 * Parts of AresGate that can be healthy or not, each with its state in words and a shape as well
 * as a colour, what it says about itself and, where there is a page for it, a way there.
 */
defineProps<{ parts: readonly Part[] }>()

/** How each state of a part looks. */
const STATES = {
  ok: { label: 'Working', color: 'success', icon: CircleCheck },
  problem: { label: 'Problem', color: 'error', icon: CircleAlert },
  unknown: { label: 'Not tested yet', color: 'warning', icon: CircleDashed },
  off: { label: 'Off', color: undefined, icon: Unplug },
} as const satisfies Record<PartState, object>

/** A collector that is waiting hasn't been tested; it just hasn't run. */
function look(part: Part) {
  const state = STATES[part.state]
  return part.group === 'collector' && part.state === 'unknown'
    ? { ...state, label: 'Waiting' }
    : state
}

/** What a part says about itself, and when it last worked. */
const note = (part: Part) =>
  [part.detail, part.last_success_at && `Last worked ${formatAgo(part.last_success_at)}`]
    .filter(Boolean)
    .join(' · ')
</script>

<template>
  <ul class="part-list">
    <li v-for="part in parts" :key="part.key" class="part-list__part" data-test="part">
      <div class="part-list__text">
        <div class="text-body-large">
          <span data-test="part-name">{{ part.name }}</span>
          <v-chip
            :color="look(part).color"
            :prepend-icon="look(part).icon"
            size="small"
            variant="tonal"
            class="ml-2"
            data-test="part-state"
          >
            {{ look(part).label }}
          </v-chip>
        </div>
        <div
          v-if="note(part)"
          class="text-body-medium text-medium-emphasis"
          data-test="part-detail"
        >
          {{ note(part) }}
        </div>
      </div>
      <v-btn
        v-if="part.integration"
        variant="text"
        :append-icon="ChevronRight"
        :to="{ name: 'integration', params: { key: part.integration } }"
        :aria-label="`Open ${part.name}`"
        data-test="part-open"
      >
        Open
      </v-btn>
    </li>
  </ul>
</template>

<style scoped>
.part-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.part-list__part {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.part-list__part + .part-list__part {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.part-list__text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
