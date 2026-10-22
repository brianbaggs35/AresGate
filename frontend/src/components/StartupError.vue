<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'

defineProps<{ message: string; busy: boolean }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <v-container class="py-8" max-width="480">
    <v-card class="pa-6" data-test="startup-error">
      <h1 class="text-headline-small mb-2">AresGate isn't answering</h1>
      <p class="text-body-large text-medium-emphasis mb-6" role="alert">{{ message }}</p>
      <v-btn
        color="primary"
        variant="tonal"
        :prepend-icon="RefreshCw"
        :loading="busy"
        data-test="retry"
        @click="$emit('retry')"
      >
        Try again
      </v-btn>
    </v-card>
  </v-container>
</template>
