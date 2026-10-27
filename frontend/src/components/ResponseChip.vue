<script setup lang="ts">
import type { IncidentResponse } from '@/api/incidents'
import { RESPONSE } from '@/response'

/**
 * What was done about an incident, as a chip: the state in words with its icon, so it is never
 * only a color. An incident about a rule has no address to act on, and says nothing.
 */
defineProps<{ response: IncidentResponse }>()
</script>

<template>
  <v-chip
    v-if="response.state !== 'no_address'"
    :color="RESPONSE[response.state].color"
    :prepend-icon="RESPONSE[response.state].icon"
    variant="tonal"
    :data-state="response.state"
    data-test="incident-response"
  >
    {{ response.label }}
  </v-chip>
</template>
