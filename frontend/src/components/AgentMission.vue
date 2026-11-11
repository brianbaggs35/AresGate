<script setup lang="ts">
import { ChevronRight, Newspaper } from '@lucide/vue'
import { computed } from 'vue'

import type { Agent, AttentionItem, Briefing } from '@/api/agents'
import { agentIcon, fleetLine, severityOf } from '@/agents'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo } from '@/format'

/**
 * The agents as one team, at the top of their page: whether anything needs the owner, the latest
 * daily briefing if an agent writes one, and the findings that matter most, each leading to the
 * agent run that raised it. It says "all quiet" when it is, which is the answer most days.
 */
const props = defineProps<{
  agents: readonly Agent[]
  attention: readonly AttentionItem[]
  total: number
  briefing: Briefing | null
}>()

const line = computed(() => fleetLine(props.agents, props.total))
const more = computed(() => props.total - props.attention.length)
</script>

<template>
  <section
    class="mission"
    :class="`mission--${line.tone}`"
    aria-labelledby="mission-title"
    data-test="agents-mission"
  >
    <header class="mission__head">
      <span class="mission__pulse" aria-hidden="true" />
      <div>
        <h2 id="mission-title" class="text-label-large mission__eyebrow">Mission control</h2>
        <p class="text-headline-small mission__line" data-test="mission-line">{{ line.text }}</p>
      </div>
    </header>

    <article v-if="briefing" class="brief" data-test="mission-briefing">
      <h3 class="text-label-large brief__title">
        <v-icon :icon="Newspaper" size="16" aria-hidden="true" />
        Today's briefing
      </h3>
      <p class="text-body-large brief__text" data-test="briefing-text">{{ briefing.summary }}</p>
      <p class="text-body-small text-medium-emphasis brief__by">
        <RouterLink
          :to="{ name: 'agent', params: { id: briefing.agent_id } }"
          data-test="briefing-link"
        >
          {{ briefing.agent_name }}
        </RouterLink>
        · {{ formatAgo(briefing.finished_at) }}
      </p>
    </article>

    <ul v-if="attention.length" class="needs" data-test="mission-needs">
      <li v-for="(item, at) in attention" :key="at">
        <RouterLink
          :to="{ name: 'agent', params: { id: item.agent_id } }"
          class="need"
          data-test="mission-need"
        >
          <span class="need__icon" aria-hidden="true">
            <v-icon :icon="agentIcon(item.icon)" size="20" />
          </span>
          <span class="need__text">
            <span class="text-title-small need__title">{{ item.title }}</span>
            <span
              v-if="item.action"
              class="text-body-small need__action"
              data-test="mission-action"
            >
              {{ item.action }}
            </span>
            <span class="text-body-small text-medium-emphasis">
              {{ item.agent_name }} · {{ formatAgo(item.finished_at) }}
              <template v-if="item.status === 'ongoing'"> · still open</template>
            </span>
          </span>
          <SeverityChip :severity="severityOf(item.severity)" />
          <v-icon :icon="ChevronRight" size="20" class="need__go" aria-hidden="true" />
        </RouterLink>
      </li>
    </ul>
    <p v-if="more > 0" class="text-body-small text-medium-emphasis" data-test="mission-more">
      And {{ more }} more in the agents' latest runs.
    </p>
  </section>
</template>

<style scoped>
.mission {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1.5rem;
  background: linear-gradient(
    135deg,
    rgba(var(--v-theme-primary), 0.1),
    rgba(var(--v-theme-surface), 1) 60%
  );
}

.mission--bad {
  background: linear-gradient(
    135deg,
    rgba(var(--v-theme-error), 0.12),
    rgba(var(--v-theme-surface), 1) 60%
  );
}

.mission--good {
  background: linear-gradient(
    135deg,
    rgba(var(--v-theme-success), 0.12),
    rgba(var(--v-theme-surface), 1) 60%
  );
}

.mission__head {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.mission__eyebrow,
.mission__line {
  margin: 0;
}

.mission__eyebrow {
  color: rgba(var(--v-theme-on-surface), 0.7);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mission__pulse {
  position: relative;
  flex: none;
  width: 0.875rem;
  height: 0.875rem;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
}

.mission--bad .mission__pulse {
  background: rgb(var(--v-theme-error));
}

.mission--good .mission__pulse {
  background: rgb(var(--v-theme-success));
}

.mission__pulse::after {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: inherit;
  animation: ping 2.4s ease-out infinite;
  content: '';
}

.brief {
  padding: 1rem 1.25rem;
  border-radius: 1rem;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.brief__title,
.brief__text,
.brief__by {
  margin: 0;
}

.brief__title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.375rem;
}

.brief__by {
  margin-top: 0.5rem;
}

.needs {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.need {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: 3.5rem;
  padding: 0.625rem 0.875rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  text-decoration: none;
}

.need:hover,
.need:focus-visible {
  border-color: rgb(var(--v-theme-primary));
}

.need__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.need__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.need__title {
  overflow-wrap: anywhere;
}

.need__action {
  overflow-wrap: anywhere;
}

.need__go {
  flex: none;
  opacity: 0.6;
}

@keyframes ping {
  0% {
    opacity: 0.6;
    transform: scale(1);
  }

  80%,
  100% {
    opacity: 0;
    transform: scale(2.6);
  }
}

@media (max-width: 599px) {
  .need {
    flex-wrap: wrap;
  }

  .need__text {
    flex-basis: calc(100% - 3.5rem);
  }

  .need__go {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mission__pulse::after {
    animation: none;
  }
}
</style>
