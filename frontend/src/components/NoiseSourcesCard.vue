<script setup lang="ts">
import { ListFilter } from '@lucide/vue'

import type { Floor, NoiseSource } from '@/api/noise'
import EmptyState from '@/components/EmptyState.vue'
import SectionCard from '@/components/SectionCard.vue'
import { ALL, FLOOR_CHOICES, weekSentence } from '@/noiseFilters'

/**
 * For each program that reports alerts, the lowest severity that counts. An alert below it is
 * kept and listed in the incident, and set aside: it adds nothing to how serious or how sure the
 * incident is. The week's counts beside each say what a floor would set aside.
 */
defineProps<{
  sources: readonly NoiseSource[]
  /** The floors as they stand now (not necessarily kept). */
  floors: Readonly<Record<string, Floor>>
}>()
const emit = defineEmits<{ change: [key: string, floor: Floor | typeof ALL] }>()
</script>

<template>
  <SectionCard
    title="What each program has to be worth"
    description="A program that reports a lot of low-severity alerts can be told to count only the serious ones. What it reports below that is still listed in the incident, marked as set aside, and counts for nothing."
    data-test="sources-card"
  >
    <ul v-if="sources.length" class="sources__list" data-test="source-list">
      <li v-for="source in sources" :key="source.key" class="sources__item" data-test="source">
        <div class="sources__name">
          <h3 class="text-title-medium">{{ source.name }}</h3>
          <p class="text-body-medium text-medium-emphasis" data-test="source-week">
            {{ weekSentence(source) }}
          </p>
        </div>
        <v-select
          :model-value="floors[source.key] ?? ALL"
          :items="FLOOR_CHOICES"
          :label="`Count ${source.name} alerts from`"
          hide-details
          class="sources__select"
          data-test="source-floor"
          @update:model-value="emit('change', source.key, $event as Floor | typeof ALL)"
        />
      </li>
    </ul>
    <EmptyState
      v-else
      title="No program has reported an alert yet"
      description="A program shows up here once it has reported one, so you can see what it sends before deciding what counts."
      :icon="ListFilter"
      data-test="no-sources"
    />
  </SectionCard>
</template>

<style scoped>
.sources__list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sources__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 16rem);
  align-items: center;
  gap: 0.5rem 1.5rem;
  padding-block: 0.75rem;
}

.sources__item + .sources__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.sources__name h3,
.sources__name p {
  margin: 0;
}

@media (max-width: 599.98px) {
  .sources__item {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
