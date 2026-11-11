<script setup lang="ts">
import { CircleAlert, Play } from '@lucide/vue'
import { computed } from 'vue'

import type { Agent, RunStatus } from '@/api/agents'
import { AGENT_STATE, RUN_STATUS, agentIcon, costWords, outcome, scheduleText } from '@/agents'
import { formatAgo, formatDue } from '@/format'

/**
 * One agent at a glance: what it is, whether it is going, how its last runs went, and what the
 * last one came to. The name opens the agent; the button asks for a run now. An agent that tests
 * the network says it has to be allowed first.
 */
const props = withDefaults(defineProps<{ agent: Agent; busy?: boolean; ready?: boolean }>(), {
  ready: true,
})
defineEmits<{ run: [] }>()

const state = computed(() => AGENT_STATE[props.agent.state])
const live = computed(() => props.agent.state === 'running' || props.agent.state === 'queued')
const last = computed(() => props.agent.last_run)
const blocked = computed(() => props.agent.active && !props.agent.allow_active)

/** The last runs in words, because the dots alone say nothing to a screen reader. */
const history = computed(() => {
  const counts = new Map<RunStatus, number>()
  for (const status of props.agent.recent) counts.set(status, (counts.get(status) ?? 0) + 1)
  if (counts.size === 0) return 'It has not run yet.'
  const parts = [...counts].map(
    ([status, count]) => `${count} ${RUN_STATUS[status].label.toLowerCase()}`,
  )
  return `Its last ${props.agent.recent.length} runs: ${parts.join(', ')}.`
})

const when = computed(() => {
  const run = last.value
  if (live.value) return ''
  if (run?.finished_at) return `Ran ${formatAgo(run.finished_at)}`
  if (props.agent.next_run_at && props.agent.enabled) {
    return `Runs ${formatDue(props.agent.next_run_at)}`
  }
  return ''
})
</script>

<template>
  <v-card class="agent" :class="{ 'agent--live': live }" data-test="agent-card">
    <div class="agent__top">
      <span class="agent__icon" aria-hidden="true">
        <v-icon :icon="agentIcon(agent.icon)" size="24" />
      </span>
      <v-chip
        :color="state.color"
        :prepend-icon="state.icon"
        size="small"
        variant="tonal"
        :class="{ agent__spin: agent.state === 'running' }"
        data-test="agent-state"
      >
        {{ state.label }}
      </v-chip>
    </div>

    <h3 class="text-title-large agent__name">
      <RouterLink
        :to="{ name: 'agent', params: { id: agent.id } }"
        class="agent__link"
        data-test="agent-open"
      >
        {{ agent.name }}
      </RouterLink>
    </h3>
    <p class="text-body-medium text-medium-emphasis agent__kind" data-test="agent-kind">
      {{ agent.template_name }} ·
      {{
        agent.enabled || agent.interval_minutes === null
          ? scheduleText(agent.interval_minutes)
          : 'Paused'
      }}
    </p>

    <div class="agent__runs" data-test="agent-recent">
      <span class="sr-only" data-test="agent-recent-text">{{ history }}</span>
      <span
        v-for="(status, at) in agent.recent"
        :key="at"
        class="agent__dot"
        :class="`agent__dot--${status}`"
        aria-hidden="true"
        data-test="agent-dot"
      />
      <span
        v-if="!agent.recent.length"
        class="agent__none text-body-small text-medium-emphasis"
        aria-hidden="true"
      >
        No runs yet
      </span>
    </div>

    <p class="text-body-medium agent__outcome" data-test="agent-outcome">
      <template v-if="last">{{ outcome(last) }}</template>
      <template v-else>Start it to see what it finds.</template>
      <span v-if="when" class="text-medium-emphasis"> · {{ when }}</span>
    </p>

    <p v-if="!ready" class="text-body-small agent__setup" data-test="agent-needs-setup">
      <v-icon :icon="CircleAlert" size="16" color="warning" aria-hidden="true" />
      It needs a little setup first.
    </p>

    <p
      v-if="agent.usage.calls"
      class="text-body-small text-medium-emphasis agent__cost"
      data-test="agent-cost"
    >
      {{ costWords(agent.usage) }} in 30 days
    </p>

    <p v-if="agent.proposals" class="text-body-small agent__proposals" data-test="agent-proposals">
      {{ agent.proposals === 1 ? '1 clean-up is' : `${agent.proposals} clean-ups are` }} waiting for
      you.
    </p>

    <div class="agent__actions">
      <v-btn
        variant="tonal"
        :prepend-icon="Play"
        :disabled="live || blocked || busy"
        :loading="busy"
        data-test="agent-run"
        @click="$emit('run')"
      >
        Run now
      </v-btn>
      <span v-if="blocked" class="text-body-small text-medium-emphasis" data-test="agent-blocked">
        Allow it to test the network first.
      </span>
    </div>
  </v-card>
</template>

<style scoped>
.agent {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1.25rem;
  transition: border-color 0.25s;
}

.agent--live {
  border: 1px solid rgb(var(--v-theme-primary));
}

.agent__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.agent__icon {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 0.875rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.agent__setup {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0;
}

.agent__name,
.agent__kind,
.agent__outcome {
  margin: 0;
}

.agent__link {
  color: inherit;
  text-decoration: none;
}

/* The whole card opens the agent, but the button above it stays a button. */
.agent__link::after {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  content: '';
}

.agent__link:focus-visible {
  outline: none;
}

.agent__link:focus-visible::after {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.agent__runs {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-height: 1.25rem;
  margin: 0.25rem 0;
}

.agent__dot {
  width: 0.5rem;
  height: 1.25rem;
  border-radius: 0.25rem;
  background: rgba(var(--v-theme-on-surface), 0.25);
}

.agent__dot--succeeded {
  background: rgb(var(--v-theme-success));
}

.agent__dot--failed {
  background: rgb(var(--v-theme-error));
}

.agent__dot--cancelled {
  background: rgb(var(--v-theme-warning));
}

.agent__dot--running,
.agent__dot--queued {
  background: rgb(var(--v-theme-primary));
}

.agent__outcome {
  flex: 1;
  overflow-wrap: anywhere;
}

.agent__actions {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.agent__spin :deep(.v-chip__prepend svg) {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent__spin :deep(.v-chip__prepend svg) {
    animation: none;
  }
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
