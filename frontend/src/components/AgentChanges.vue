<script setup lang="ts">
import { CircleCheck, Plus, Repeat } from '@lucide/vue'
import { computed } from 'vue'

import type { Changes, Finding } from '@/api/agents'
import { severityOf } from '@/agents'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatCount } from '@/format'

/**
 * How a run differs from the one before it: what is new, what is still open and what the agent
 * reported last time and no longer does, which is good news worth saying. A run with nothing before
 * it to compare with says nothing.
 */
const props = defineProps<{ changes: Changes; findings: readonly Finding[] }>()

const fresh = computed(() => props.findings.filter((found) => found.status === 'new').length)
const open = computed(() => props.findings.length - fresh.value)
const count = (value: number, one: string) => `${formatCount(value)} ${one}`
</script>

<template>
  <section class="changes" aria-labelledby="changes-title" data-test="agent-changes">
    <h3 id="changes-title" class="text-label-large changes__title">
      Since its run {{ formatAgo(changes.since) }}
    </h3>
    <ul class="changes__counts">
      <li class="changes__count" data-test="changes-new">
        <v-icon :icon="Plus" size="18" color="primary" aria-hidden="true" />
        {{ count(fresh, 'new') }}
      </li>
      <li class="changes__count" data-test="changes-open">
        <v-icon :icon="Repeat" size="18" aria-hidden="true" />
        {{ count(open, 'still open') }}
      </li>
      <li class="changes__count" data-test="changes-gone">
        <v-icon :icon="CircleCheck" size="18" color="success" aria-hidden="true" />
        {{ count(changes.gone.length, 'no longer reported') }}
      </li>
    </ul>
    <ul v-if="changes.gone.length" class="changes__gone" data-test="changes-gone-list">
      <li v-for="(item, at) in changes.gone" :key="at" class="text-body-medium">
        <SeverityChip :severity="severityOf(item.severity)" />
        <span class="changes__what">{{ item.title }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.changes {
  padding: 0.875rem 1rem;
  border-radius: 1rem;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.changes__title {
  margin: 0 0 0.5rem;
}

.changes__counts,
.changes__gone {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.changes__count {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.changes__gone {
  flex-direction: column;
  margin-top: 0.75rem;
}

.changes__gone li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.changes__what {
  text-decoration: line-through;
  text-decoration-color: rgba(var(--v-theme-on-surface), 0.4);
  overflow-wrap: anywhere;
}
</style>
