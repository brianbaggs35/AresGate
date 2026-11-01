<script setup lang="ts">
import type { Glance } from '@/api/incidents'
import { CLASSIFICATION } from '@/triage'

/**
 * What the AI made of an incident, as a chip for a list: its word for it, and how sure it is. It
 * says it is the AI's, since AresGate's own confidence is shown beside it.
 */
defineProps<{ ai: Glance }>()
</script>

<template>
  <v-chip
    :color="CLASSIFICATION[ai.classification].color"
    :prepend-icon="CLASSIFICATION[ai.classification].icon"
    :title="`The AI's opinion: ${CLASSIFICATION[ai.classification].meaning}`"
    variant="outlined"
    data-test="ai-chip"
  >
    AI: {{ CLASSIFICATION[ai.classification].label }}, {{ ai.confidence }}% sure
  </v-chip>
</template>
