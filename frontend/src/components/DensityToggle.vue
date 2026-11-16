<script setup lang="ts">
import { Rows3, Rows4 } from '@lucide/vue'

import { useDensityStore, type Density } from '@/stores/density'

/**
 * The choice between a roomy list and a compact one, for the pages people read for a long time
 * (the incidents and the logs). It is remembered in this browser and applies to both.
 */
const density = useDensityStore()
</script>

<template>
  <v-btn-toggle
    :model-value="density.preference"
    mandatory
    divided
    density="comfortable"
    variant="outlined"
    color="primary"
    aria-label="Density"
    data-test="density"
    @update:model-value="density.setPreference($event as Density)"
  >
    <v-btn
      value="comfortable"
      :icon="Rows3"
      aria-label="Comfortable"
      title="Comfortable"
      data-test="density-comfortable"
    />
    <v-btn
      value="compact"
      :icon="Rows4"
      aria-label="Compact"
      title="Compact"
      data-test="density-compact"
    />
  </v-btn-toggle>
</template>
