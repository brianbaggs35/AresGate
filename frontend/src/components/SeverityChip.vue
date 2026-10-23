<script setup lang="ts">
import { SEVERITY, type Severity } from '@/severity'

defineProps<{ severity: Severity }>()
</script>

<template>
  <v-chip
    :color="SEVERITY[severity].color"
    :prepend-icon="SEVERITY[severity].icon"
    :variant="SEVERITY[severity].variant"
    data-test="severity"
  >
    {{ SEVERITY[severity].label }}
  </v-chip>
</template>
