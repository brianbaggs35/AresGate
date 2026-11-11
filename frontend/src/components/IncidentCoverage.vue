<script setup lang="ts">
import { Check, PlugZap } from '@lucide/vue'

import type { MissingProgram, Program } from '@/api/incidents'
import SectionCard from '@/components/SectionCard.vue'

/**
 * Which programs this incident came from, and which that are not connected would add to it, and
 * what: a program that is not connected is a view of the network that AresGate does without, and
 * every one that is connected makes an incident say more. Each of those is drawn as a tile, the
 * ones that reported first, and the others with a way to connect them.
 */
defineProps<{
  /** The programs that reported part of the incident. */
  sources: readonly Program[]
  /** The integrations that are not connected. */
  missing: readonly MissingProgram[]
}>()
</script>

<template>
  <SectionCard
    title="What more connecting would show"
    description="Each program sees the network its own way. The more of them are connected, the more an incident says: who talked to whom, what was sent, what it was matched to."
    data-test="coverage-card"
  >
    <ul class="coverage" data-test="coverage">
      <li
        v-for="source in sources"
        :key="source.key"
        class="coverage__tile coverage__tile--seen"
        data-test="coverage-seen"
      >
        <v-icon :icon="Check" size="20" color="success" aria-hidden="true" />
        <div>
          <h3 class="text-title-medium" data-test="coverage-name">{{ source.name }}</h3>
          <p class="text-body-medium text-medium-emphasis">Reported part of this incident.</p>
        </div>
      </li>
      <li
        v-for="program in missing"
        :key="program.source"
        class="coverage__tile coverage__tile--missing"
        data-test="coverage-missing"
      >
        <v-icon :icon="PlugZap" size="20" aria-hidden="true" />
        <div>
          <h3 class="text-title-medium" data-test="coverage-name">{{ program.source_name }}</h3>
          <p class="text-body-medium text-medium-emphasis">
            Not connected. Would add: {{ program.adds }}
          </p>
          <v-btn
            variant="text"
            size="small"
            :to="{ name: 'integration', params: { key: program.source } }"
            :data-test="`coverage-connect-${program.source}`"
          >
            Connect {{ program.source_name }}
          </v-btn>
        </div>
      </li>
    </ul>
  </SectionCard>
</template>

<style scoped>
.coverage {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.coverage__tile {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.coverage__tile--missing {
  border-style: dashed;
}

.coverage__tile h3,
.coverage__tile p {
  margin: 0;
}
</style>
