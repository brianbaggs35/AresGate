<script setup lang="ts">
import { Bot } from '@lucide/vue'
import { computed } from 'vue'

import type { ClearedCounts } from '@/api/aiCleared'
import { nudgeText } from '@/cleared'

/**
 * Says on the dashboard that the AI has cleared incidents, or suggests clearing some, that the
 * owner has not looked at, and takes them to the page for it. What the AI clears by itself is
 * always said here, so it never goes unseen. With nothing to say it is not there.
 */
const props = defineProps<{ counts: ClearedCounts }>()
const text = computed(() => nudgeText(props.counts))
const to = computed(() => ({
  name: 'cleared',
  query: props.counts.cleared > 0 ? { state: 'cleared' } : undefined,
}))
</script>

<template>
  <v-alert v-if="text" variant="tonal" color="info" :icon="Bot" data-test="cleared-nudge">
    <span data-test="cleared-nudge-text">{{ text }}</span>
    <template #append>
      <v-btn variant="flat" color="primary" :to="to" data-test="cleared-nudge-open">Look</v-btn>
    </template>
  </v-alert>
</template>
