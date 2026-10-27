<script setup lang="ts">
import type { VerdictKind } from '@/api/verdicts'
import { VERDICT } from '@/verdicts'

/** What the owner said of something, as a chip with its icon and its name. */
withDefaults(defineProps<{ verdict: VerdictKind; size?: 'x-small' | 'small' | 'default' }>(), {
  size: 'default',
})
</script>

<template>
  <v-chip
    :color="VERDICT[verdict].color"
    :prepend-icon="VERDICT[verdict].icon"
    :size="size"
    :title="VERDICT[verdict].meaning"
    variant="tonal"
    data-test="verdict"
  >
    {{ VERDICT[verdict].label }}
  </v-chip>
</template>
