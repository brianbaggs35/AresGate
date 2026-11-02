<script setup lang="ts">
import type { AssetStatus } from '@/api/assets'
import { STATUS } from '@/inventory'

defineProps<{ status: AssetStatus }>()
</script>

<template>
  <v-chip
    :color="STATUS[status].color"
    :prepend-icon="STATUS[status].icon"
    variant="tonal"
    data-test="asset-status"
  >
    {{ STATUS[status].label }}
  </v-chip>
</template>
