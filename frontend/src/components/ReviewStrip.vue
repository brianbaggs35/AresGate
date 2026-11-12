<script setup lang="ts">
import { computed } from 'vue'

import type { Classification, ReviewState } from '@/api/incidents'
import type { DecisionSubject } from '@/api/review'
import ReviewAnswer from '@/components/ReviewAnswer.vue'
import { REVIEW } from '@/review'

/**
 * Where the owner's review of an AI's call stands, beside the call itself, and the means to
 * answer it: on an incident for the AI's reading of it, and on a kind for its judgement of the
 * kind. A call that changes nothing (it is unclear, or not a call at all) has nothing to review.
 */
const props = defineProps<{
  subject: DecisionSubject
  id: number
  kind: Classification
  review: ReviewState
}>()
defineEmits<{ answered: [] }>()

const reviewable = computed(() => props.kind !== 'unclear')
const state = computed(() => REVIEW[props.review])
</script>

<template>
  <section v-if="reviewable" class="strip" aria-label="Your review" data-test="review-strip">
    <p class="text-body-large strip__state" data-test="strip-state">
      <v-icon :icon="state.icon" :color="state.color" size="20" aria-hidden="true" />
      <span>
        <b>{{ state.label }}.</b> {{ state.meaning }}
      </span>
    </p>
    <ReviewAnswer
      :id="id"
      :subject="subject"
      :kind="kind"
      :review="review"
      @answered="$emit('answered')"
    />
  </section>
</template>

<style scoped>
.strip {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-self: stretch;
  padding: 1rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.strip__state {
  display: flex;
  gap: 0.5rem;
  margin: 0;
}
</style>
