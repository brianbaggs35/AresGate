<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { computed } from 'vue'

import type { Activity, Performance } from '@/api/agents'
import { RUN_STATUS, agentIcon, finishedShare, nodeInfo, outcome } from '@/agents'
import { formatAgo, formatCount, formatSpan } from '@/format'

/**
 * What the agents have been doing, as one feed: how their runs went over the last 30 days, and
 * the latest runs of all of them, each with where it is now or what it came to. Each leads to the
 * agent. Nothing is shown before an agent has run.
 */
const props = defineProps<{ activity: readonly Activity[]; performance: Performance }>()

const share = computed(() => finishedShare(props.performance))
const tiles = computed(() => [
  { key: 'runs', label: 'Runs in 30 days', value: formatCount(props.performance.finished) },
  { key: 'share', label: 'Finished', value: share.value === null ? '–' : `${share.value}%` },
  {
    key: 'time',
    label: 'Average run',
    value:
      props.performance.average_seconds === null
        ? '–'
        : formatSpan(props.performance.average_seconds),
  },
  { key: 'findings', label: 'Findings raised', value: formatCount(props.performance.findings) },
])

/** When a run was last heard of: it ended, it began, or it was asked for. */
const moment = (item: Activity) =>
  item.run.finished_at ?? item.run.started_at ?? item.run.requested_at

/** Where a run that is going has got to, or what it came to. */
const words = (item: Activity) =>
  item.run.status === 'running' && item.run.node
    ? `${nodeInfo(item.run.node).label} · ${nodeInfo(item.run.node).hint}`
    : outcome(item.run)
</script>

<template>
  <section
    v-if="activity.length"
    class="team"
    aria-labelledby="team-title"
    data-test="agents-activity"
  >
    <h2 id="team-title" class="text-title-medium">What the team has been doing</h2>

    <dl class="tiles" data-test="activity-tiles">
      <div v-for="tile in tiles" :key="tile.key" class="tile" :data-test="`activity-${tile.key}`">
        <dt class="text-body-small text-medium-emphasis">{{ tile.label }}</dt>
        <dd class="text-headline-small tile__value">{{ tile.value }}</dd>
      </div>
    </dl>

    <ul class="feed" data-test="activity-feed">
      <li v-for="item in activity" :key="item.run.id">
        <RouterLink
          :to="{ name: 'agent', params: { id: item.agent_id } }"
          class="entry"
          data-test="activity-entry"
        >
          <span class="entry__icon" aria-hidden="true">
            <v-icon :icon="agentIcon(item.icon)" size="20" />
          </span>
          <span class="entry__text">
            <span class="text-title-small entry__name">{{ item.agent_name }}</span>
            <span
              class="text-body-small text-medium-emphasis entry__words"
              data-test="activity-words"
            >
              {{ words(item) }}
            </span>
          </span>
          <v-chip
            :color="RUN_STATUS[item.run.status].color"
            :prepend-icon="RUN_STATUS[item.run.status].icon"
            size="small"
            variant="tonal"
            :class="{ entry__spin: item.run.status === 'running' }"
            data-test="activity-status"
          >
            {{ RUN_STATUS[item.run.status].label }}
          </v-chip>
          <span class="text-body-small text-medium-emphasis entry__ago" data-test="activity-ago">
            {{ formatAgo(moment(item)) }}
          </span>
          <v-icon :icon="ChevronRight" size="20" class="entry__go" aria-hidden="true" />
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.team {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  padding: 1.25rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1.5rem;
  container-type: inline-size;
}

.team h2 {
  margin: 0;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(9rem, 100%), 1fr));
  gap: 0.75rem;
  margin: 0;
}

.tile {
  padding: 0.75rem 1rem;
  border-radius: 1rem;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.tile dt,
.tile dd {
  margin: 0;
}

.tile__value {
  font-variant-numeric: tabular-nums;
}

.feed {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.entry {
  display: grid;
  grid-template-columns: auto 1fr auto auto auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.625rem;
  border-radius: 0.875rem;
  color: inherit;
  text-decoration: none;
  transition: background-color 0.2s;
}

.entry:hover,
.entry:focus-visible {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.entry__icon {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.entry__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.entry__name,
.entry__words {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry__go {
  color: rgba(var(--v-theme-on-surface), 0.5);
}

@media (prefers-reduced-motion: no-preference) {
  .entry__spin :deep(.v-icon) {
    animation: spin 1.2s linear infinite;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* On a narrow card the time and the arrow give way, so the name and the status still fit. */
@container (max-width: 34rem) {
  .entry {
    grid-template-columns: auto 1fr auto;
  }

  .entry__ago,
  .entry__go {
    display: none;
  }
}
</style>
