<script setup lang="ts">
import type { Lane } from '@/api/incidents'
import { LANE } from '@/threats'

/**
 * Where an incident stands: a threat, a suspect or background. A word and an icon as well as a
 * color, as with severity, so it does not rest on telling colors apart.
 */
defineProps<{ lane: Lane }>()
</script>

<template>
  <v-chip
    :color="LANE[lane].color"
    :prepend-icon="LANE[lane].icon"
    :variant="lane === 'background' ? 'outlined' : 'flat'"
    :title="LANE[lane].meaning"
    data-test="lane-chip"
  >
    {{ LANE[lane].label }}
  </v-chip>
</template>
