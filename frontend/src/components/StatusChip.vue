<script setup lang="ts">
import type { Status } from '@/api/integrations'
import { STATUS } from '@/integrations'

defineProps<{ status: Status }>()
</script>

<template>
  <v-chip
    :color="STATUS[status].color"
    :prepend-icon="STATUS[status].icon"
    variant="tonal"
    data-test="status"
  >
    {{ STATUS[status].label }}
  </v-chip>
</template>
