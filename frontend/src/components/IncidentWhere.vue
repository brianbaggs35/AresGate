<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'

import type { IncidentDetail } from '@/api/incidents'
import CallChip from '@/components/CallChip.vue'
import LaneChip from '@/components/LaneChip.vue'
import SectionCard from '@/components/SectionCard.vue'
import StageTrail from '@/components/StageTrail.vue'
import { callSentence, LANE, reachOf, verdictOf } from '@/threats'

/**
 * Where an incident stands and why: its lane, each fact that put it there, how far an attack
 * got, and the kind of incident it is, which is what the AI judges. It is the answer to "why is
 * this a threat?", or "why isn't it?", in words anyone can check.
 */
defineProps<{ incident: IncidentDetail }>()
</script>

<template>
  <SectionCard
    title="Where it stands"
    description="Whether AresGate calls it a threat, a suspect or background, and each fact that decided it."
    data-test="where-card"
  >
    <div class="where__lane">
      <template v-if="incident.lane">
        <LaneChip :lane="incident.lane" />
        <p class="text-body-large" data-test="where-meaning">{{ LANE[incident.lane].meaning }}</p>
      </template>
      <p v-else class="text-body-large" data-test="where-none">
        It is not in a lane: it is over, or you said it is not suspicious or low priority.
      </p>
    </div>

    <ul v-if="incident.why.length" class="where__why text-body-large">
      <li v-for="line in incident.why" :key="line" data-test="where-why">{{ line }}</li>
    </ul>

    <div class="where__row">
      <h3 class="text-label-large">How far it got</h3>
      <StageTrail :stages="incident.stages" />
    </div>

    <div v-if="incident.call" class="where__row" data-test="where-call">
      <h3 class="text-label-large">What is made of it beyond the rules</h3>
      <div class="where__call">
        <CallChip :call="incident.call" />
        <p class="text-body-medium text-medium-emphasis">{{ callSentence(incident.call) }}</p>
      </div>
    </div>

    <div v-if="incident.family" class="where__row" data-test="where-family">
      <h3 class="text-label-large">Its kind</h3>
      <p class="text-body-large where__label" data-test="where-label">
        {{ incident.family.label }}
      </p>
      <p class="text-body-medium text-medium-emphasis">
        {{ reachOf(incident.family.reach).label }}. {{ verdictOf(incident.family).text }}.
        {{ incident.family.incidents }}
        {{ incident.family.incidents === 1 ? 'incident' : 'incidents' }} of it
        {{ incident.family.incidents === 1 ? 'is' : 'are' }} going on.
      </p>
      <v-btn
        variant="text"
        :append-icon="ArrowRight"
        :to="{ name: 'family', params: { id: incident.family.id } }"
        class="where__open"
        data-test="where-open"
      >
        Open the kind
      </v-btn>
    </div>
  </SectionCard>
</template>

<style scoped>
.where__lane {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.where__lane p,
.where__call p,
.where__row p,
.where__row h3 {
  margin: 0;
}

.where__why {
  margin: 1rem 0 0;
  padding-inline-start: 1.25rem;
}

.where__row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  margin-top: 1.25rem;
}

.where__call {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.where__label {
  overflow-wrap: anywhere;
}

.where__open {
  margin-inline-start: -0.75rem;
}
</style>
