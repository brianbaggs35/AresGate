<script setup lang="ts">
import { computed } from 'vue'

import type { Run } from '@/api/agents'
import { findingsOverTime } from '@/agents'
import BarChart from '@/charts/BarChart.vue'

/**
 * Whether an agent is finding more or less: a bar for each of its last runs that finished, split by
 * how serious. A quiet agent has no bars to draw, and says so.
 */
const props = defineProps<{ runs: readonly Run[] }>()

const over = computed(() => findingsOverTime(props.runs))
</script>

<template>
  <BarChart
    title="What it found, run by run"
    caption="Findings in each of its last runs, by how serious"
    category-label="Run"
    :categories="over.categories"
    :series="over.series"
    orientation="vertical"
    stacked
    whole
    :height="200"
    empty-title="Nothing to chart yet"
    empty-description="Once it has run and found something, each run is a bar here."
    data-test="agent-trend"
  />
</template>
