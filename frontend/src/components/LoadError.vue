<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'

/**
 * What a page or a panel shows when it could not load what it needs: in words, with a way to try
 * again. The same alert is used for every failed load, so people learn what it looks like.
 */
withDefaults(
  defineProps<{
    message: string
    /** The retry is under way. */
    loading?: boolean
    /** Some failures won't change by asking again, such as a page that doesn't exist. */
    canRetry?: boolean
    /** For tests to tell one retry button from another. */
    retryTestId?: string
  }>(),
  { loading: false, canRetry: true, retryTestId: 'retry' },
)
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <v-alert type="error" variant="tonal" role="alert">
    <span data-test="load-error-message">{{ message }}</span>
    <template v-if="canRetry" #append>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        :data-test="retryTestId"
        @click="emit('retry')"
      >
        Try again
      </v-btn>
    </template>
  </v-alert>
</template>
