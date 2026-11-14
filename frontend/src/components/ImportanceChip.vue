<script setup lang="ts">
import { Gem, ShieldCheck, TriangleAlert } from '@lucide/vue'
import { computed } from 'vue'

import type { Touched } from '@/api/incidents'

/**
 * Why an incident is ranked where it is, in a word: it touched a device the owner said is
 * critical or important, or only a guest's or an IoT device, which takes more proof. Nothing for
 * an incident that touched nothing that matters either way. The sentence that says which device
 * is the chip's title.
 */
const props = defineProps<{ touched: Touched }>()

const LOOK = {
  critical: { label: 'Critical device', color: 'error', icon: Gem, variant: 'flat' },
  important: { label: 'Important device', color: 'warning', icon: TriangleAlert, variant: 'flat' },
  low: { label: 'Guest or IoT only', color: 'secondary', icon: ShieldCheck, variant: 'outlined' },
} as const

const look = computed(() => LOOK[props.touched.importance])
</script>

<template>
  <v-chip
    :color="look.color"
    :prepend-icon="look.icon"
    :variant="look.variant"
    :title="touched.text"
    data-test="importance-chip"
  >
    {{ look.label }}
  </v-chip>
</template>
