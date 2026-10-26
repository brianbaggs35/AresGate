<script setup lang="ts">
import { Ban, Layers } from '@lucide/vue'
import { computed } from 'vue'

import type { Incident } from '@/api/incidents'
import ConfidenceMeter from '@/components/ConfidenceMeter.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { isAboutRule, otherAddresses, spanOf } from '@/incidents'
import { SEVERITY } from '@/severity'

/**
 * An incident in a list: how serious it is, what it is, how sure AresGate is and which programs
 * saw it. The whole card leads to the incident.
 */
const props = defineProps<{ incident: Incident }>()

const accent = computed(() => `rgb(var(--v-theme-${SEVERITY[props.incident.severity].color}))`)
const others = computed(() => otherAddresses(props.incident).length)
const signals = computed(() => {
  const count = props.incident.signal_count
  if (count === 1) return '1 signal'
  return `${formatCount(count)} signals ${spanOf(props.incident)}`
})
</script>

<template>
  <v-card
    :to="{ name: 'incident', params: { id: incident.id } }"
    hover
    class="incident-card pa-4 pa-sm-5"
    :style="{ '--incident-accent': accent }"
    data-test="incident"
  >
    <div class="incident-card__top">
      <SeverityChip :severity="incident.severity" />
      <IncidentStatusChip v-if="incident.status !== 'open'" :status="incident.status" />
      <v-chip
        v-if="incident.banned"
        :prepend-icon="Ban"
        variant="tonal"
        data-test="incident-banned"
      >
        Banned
      </v-chip>
      <span class="incident-card__when text-body-medium text-medium-emphasis">
        Last signal
        <time
          :datetime="incident.last_seen_at"
          :title="formatDateTime(incident.last_seen_at)"
          data-test="incident-when"
          >{{ formatAgo(incident.last_seen_at) }}</time
        >
      </span>
    </div>

    <h3 class="incident-card__title text-title-large" data-test="incident-title">
      {{ incident.title }}
    </h3>

    <div class="incident-card__details">
      <ConfidenceMeter
        class="incident-card__confidence"
        :confidence="incident.confidence"
        :level="incident.confidence_level"
      />
      <ul class="incident-card__facts text-body-medium text-medium-emphasis">
        <li class="incident-card__fact" data-test="incident-signals">
          <v-icon :icon="Layers" size="18" aria-hidden="true" />
          {{ signals }}
        </li>
        <li class="incident-card__fact" data-test="incident-programs">
          <span class="text-medium-emphasis">Seen by</span>
          {{ incident.sources.map(({ name }) => name).join(', ') }}
        </li>
        <li class="incident-card__fact" data-test="incident-subject">
          <span class="incident-card__subject">{{
            isAboutRule(incident.subject) ? 'A rule with no address' : incident.subject
          }}</span>
          <template v-if="others > 0">
            and {{ others }} other {{ others === 1 ? 'address' : 'addresses' }}
          </template>
        </li>
      </ul>
    </div>
  </v-card>
</template>

<style scoped>
.incident-card {
  position: relative;
  display: block;
  text-decoration: none;
  color: inherit;
  overflow: hidden;
}

/* The bar on the left says how serious it is at a glance, and the chip says it in words. */
.incident-card::before {
  content: '';
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 4px;
  background: var(--incident-accent);
}

.incident-card__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.incident-card__when {
  margin-inline-start: auto;
}

.incident-card__title {
  margin: 0.75rem 0 0.75rem;
  overflow-wrap: anywhere;
}

.incident-card__details {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem 2rem;
  align-items: center;
}

.incident-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.incident-card__fact {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  overflow-wrap: anywhere;
}

.incident-card__subject {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@media (min-width: 720px) {
  .incident-card__details {
    grid-template-columns: minmax(12rem, 16rem) minmax(0, 1fr);
  }
}
</style>
