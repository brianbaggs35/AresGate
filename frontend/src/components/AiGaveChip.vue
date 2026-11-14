<script setup lang="ts">
import { Bot } from '@lucide/vue'
import { computed } from 'vue'

import type { GivenByAi } from '@/api/verdicts'

/**
 * Says that the AI, and not the owner, gave a verdict, and how sure it was. The provider and the
 * model are in the tooltip, for whoever wants to know which one said so.
 */
const props = defineProps<{ ai: Pick<GivenByAi, 'confidence' | 'provider' | 'model'> }>()

const who = computed(() => [props.ai.provider, props.ai.model].filter(Boolean).join(' '))
const title = computed(() => (who.value ? `Said by ${who.value}` : 'Said by the AI'))
</script>

<template>
  <v-chip
    color="info"
    size="small"
    variant="tonal"
    :prepend-icon="Bot"
    :title="title"
    data-test="ai-gave"
  >
    Given by the AI, {{ ai.confidence }}% sure
  </v-chip>
</template>
