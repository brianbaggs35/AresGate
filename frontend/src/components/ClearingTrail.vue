<script setup lang="ts">
import type { ClearingStep } from '@/api/incidents'
import { stepLine } from '@/cleared'
import { formatDateTime } from '@/format'

/**
 * What happened to the AI clearing an incident, in order: it cleared the incident or suggested
 * it, and what the owner did about that. Not there for an incident the AI never had a say in.
 */
defineProps<{ steps: readonly ClearingStep[] }>()
</script>

<template>
  <v-card v-if="steps.length" class="pa-5 pa-sm-6" data-test="clearing-trail">
    <h2 class="text-title-large">The AI clearing this</h2>
    <ol class="trail" data-test="clearing-steps">
      <li v-for="step in steps" :key="`${step.action}-${step.at}`" class="text-body-large">
        {{ stepLine(step) }}
        <time class="text-medium-emphasis text-body-medium" :datetime="step.at">
          {{ formatDateTime(step.at) }}
        </time>
      </li>
    </ol>
  </v-card>
</template>

<style scoped>
.trail {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding-inline-start: 1.25rem;
}
</style>
