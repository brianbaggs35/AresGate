<script setup lang="ts">
import type { IncidentStatus } from '@/api/incidents'
import { STATUS } from '@/incidents'

defineProps<{ status: IncidentStatus }>()
</script>

<template>
  <v-chip
    :color="STATUS[status].color"
    :prepend-icon="STATUS[status].icon"
    variant="tonal"
    data-test="incident-status"
  >
    {{ STATUS[status].label }}
  </v-chip>
</template>
