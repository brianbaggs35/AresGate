<script setup lang="ts">
import { Radar } from '@lucide/vue'
import { computed } from 'vue'

import type { HunterFlag } from '@/api/incidents'

/**
 * Says that the threat hunter flagged an incident in its last run, by name. The hunter only reads,
 * so this is its opinion, shown beside AresGate's own: the confidence on the card is not changed
 * by it.
 */
const props = defineProps<{ flags: readonly HunterFlag[] }>()

const first = computed(() => props.flags[0])
const title = computed(() =>
  props.flags.map((flag) => `${flag.agent_name} (${flag.severity}): ${flag.title}`).join('\n'),
)
</script>

<template>
  <v-chip
    v-if="first"
    color="warning"
    variant="outlined"
    :prepend-icon="Radar"
    :title="title"
    data-test="hunter-chip"
  >
    Flagged by {{ first.agent_name }}
  </v-chip>
</template>
