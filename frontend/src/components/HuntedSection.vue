<script setup lang="ts">
import { ArrowRight, Radar } from '@lucide/vue'

import type { HuntedPage } from '@/api/threats'
import SeverityChip from '@/components/SeverityChip.vue'
import { SEVERITIES, type Severity } from '@/severity'
import { formatCount } from '@/format'

/**
 * What the threat hunter flagged among the incidents going on, on the Threats page. The hunter
 * only reads, so these are not a lane: they are what it thinks is worth your attention, wherever
 * AresGate's own rules put the incident, with what it suggests, and a way to see them all.
 */
defineProps<{ hunted: HuntedPage }>()

const severityOf = (name: string): Severity => SEVERITIES.find((known) => known === name) ?? 'info'
</script>

<template>
  <section v-if="hunted.total > 0" class="hunted" aria-labelledby="hunted-title" data-test="hunted">
    <h2 id="hunted-title" class="text-title-large hunted__title">
      <v-icon :icon="Radar" size="22" aria-hidden="true" />
      The threat hunter flagged {{ formatCount(hunted.total) }}
      {{ hunted.total === 1 ? 'incident' : 'incidents' }}
    </h2>
    <p class="text-body-medium text-medium-emphasis">
      It reads what is going on and says what it thinks is worth your attention. Its word is its
      own: it does not change where AresGate puts an incident.
    </p>
    <ul class="hunted__list">
      <li v-for="item in hunted.items" :key="item.id" data-test="hunted-item">
        <SeverityChip :severity="severityOf(item.severity)" />
        <div class="hunted__what">
          <v-btn
            variant="text"
            class="hunted__open"
            :to="{ name: 'incident', params: { id: item.id } }"
            data-test="hunted-open"
          >
            {{ item.title }}
          </v-btn>
          <span class="text-body-medium text-medium-emphasis" data-test="hunted-finding">
            {{ item.agent_name }}: {{ item.finding }}
          </span>
          <span v-if="item.action" class="text-body-medium" data-test="hunted-action">
            What to do: {{ item.action }}
          </span>
        </div>
      </li>
    </ul>
    <v-btn
      variant="tonal"
      :append-icon="ArrowRight"
      :to="{ name: 'incidents', query: { q: 'hunted:yes' } }"
      data-test="hunted-all"
    >
      See all {{ formatCount(hunted.total) }} in Incidents
    </v-btn>
  </section>
</template>

<style scoped>
.hunted {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border: 1px solid rgba(var(--v-theme-warning), 0.5);
  border-radius: 1rem;
}

.hunted__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.hunted__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.hunted__list li {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.hunted__what {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}

.hunted__open {
  align-self: flex-start;
  height: auto;
  min-height: 2rem;
  padding-inline: 0;
  text-align: start;
  white-space: normal;
}
</style>
