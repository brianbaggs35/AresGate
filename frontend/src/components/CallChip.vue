<script setup lang="ts">
import type { Call } from '@/api/incidents'
import { BASIS } from '@/threats'
import { CLASSIFICATION } from '@/triage'

/**
 * What is made of an incident beyond AresGate's rules, and whose word it is: yours on its kind,
 * the AI's reading of it, or the AI's judgement of its kind. Like the AI's own chip it says whose
 * opinion it is, since the confidence beside it is AresGate's.
 */
defineProps<{ call: Call }>()
</script>

<template>
  <v-chip
    :color="CLASSIFICATION[call.classification].color"
    :prepend-icon="CLASSIFICATION[call.classification].icon"
    :title="`${BASIS[call.basis].sentence} ${CLASSIFICATION[call.classification].meaning}`"
    variant="outlined"
    data-test="call-chip"
  >
    {{ call.basis === 'owner' ? 'You' : 'AI' }}: {{ CLASSIFICATION[call.classification].label
    }}<template v-if="call.basis !== 'owner'">, {{ call.confidence }}% sure</template>
  </v-chip>
</template>
