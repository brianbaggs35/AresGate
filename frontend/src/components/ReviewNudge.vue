<script setup lang="ts">
import { ClipboardCheck } from '@lucide/vue'

import { useReviewStore } from '@/stores/review'

/**
 * Says on the dashboard that the AI's decisions wait for the owner, and takes them to the Review
 * page. With none waiting it is not there.
 */
const review = useReviewStore()
</script>

<template>
  <v-alert
    v-if="review.waiting > 0"
    variant="tonal"
    color="primary"
    :icon="ClipboardCheck"
    data-test="review-nudge"
  >
    <span data-test="review-nudge-text">
      The AI has decided {{ review.waiting }} {{ review.waiting === 1 ? 'thing' : 'things' }} that
      {{ review.waiting === 1 ? 'waits' : 'wait' }} for you to agree or disagree.
    </span>
    <template #append>
      <v-btn variant="flat" color="primary" :to="{ name: 'review' }" data-test="review-nudge-open">
        Review
      </v-btn>
    </template>
  </v-alert>
</template>
