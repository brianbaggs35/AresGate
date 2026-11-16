<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'

import type { HandoffList } from '@/api/agents'
import { handoffLimits } from '@/agents'
import { formatAgo } from '@/format'

/**
 * What the agents asked each other for in the last week: who asked which kind of agent to look into
 * what, and why, and whether it was made or refused (with the reason). The limits on it are said
 * above the list, so that a refusal is no surprise. The reason is what the asking agent wrote, so
 * it is shown as it is, as text.
 */
defineProps<{ list: HandoffList }>()
</script>

<template>
  <div class="handoffs" data-test="handoffs-root">
    <p class="text-body-medium text-medium-emphasis" data-test="handoffs-limits">
      {{ handoffLimits(list) }}
    </p>
    <p
      v-if="!list.handoffs.length"
      class="text-body-large text-medium-emphasis"
      data-test="handoffs-none"
    >
      No agent has asked another for help this week.
    </p>
    <ul v-else class="handoffs__list" data-test="handoffs-list">
      <li v-for="item in list.handoffs" :key="item.id" class="handoff" data-test="handoff">
        <div class="handoff__who text-body-large">
          <RouterLink
            :to="{ name: 'agent', params: { id: item.from_agent_id } }"
            data-test="handoff-from"
            >{{ item.from_agent }}</RouterLink
          >
          <v-icon :icon="ArrowRight" size="16" aria-label="asked" role="img" :aria-hidden="false" />
          <RouterLink
            v-if="item.to_agent_id !== null"
            :to="{ name: 'agent', params: { id: item.to_agent_id } }"
            data-test="handoff-to"
            >{{ item.to_agent }}</RouterLink
          >
          <span v-else data-test="handoff-to">{{ item.to_agent }}</span>
          <v-chip
            size="small"
            variant="tonal"
            :color="item.status === 'queued' ? 'success' : 'warning'"
            data-test="handoff-status"
          >
            {{ item.status === 'queued' ? 'Asked' : 'Refused' }}
          </v-chip>
          <span class="text-body-small text-medium-emphasis">{{ formatAgo(item.created_at) }}</span>
        </div>
        <p class="text-body-medium handoff__text" data-test="handoff-subject">
          About
          <RouterLink
            v-if="item.incident_id !== null"
            :to="{ name: 'incident', params: { id: item.incident_id } }"
            data-test="handoff-incident"
            >{{ item.subject }}</RouterLink
          ><template v-else>{{ item.subject }}</template
          >: {{ item.reason }}
        </p>
        <p
          v-if="item.refusal"
          class="text-body-medium text-medium-emphasis handoff__text"
          data-test="handoff-refusal"
        >
          {{ item.refusal }}
        </p>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.handoffs {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.handoffs p {
  margin: 0;
}

.handoffs__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.handoff {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.handoff__who {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.handoff__text {
  overflow-wrap: anywhere;
}
</style>
