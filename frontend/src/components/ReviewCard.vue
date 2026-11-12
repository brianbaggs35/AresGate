<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { Decision } from '@/api/review'
import ReviewAnswer from '@/components/ReviewAnswer.vue'
import { formatAgo, formatCount } from '@/format'
import { REVIEW } from '@/review'
import { CLASSIFICATION } from '@/triage'

/**
 * One decision of the AI to look at: what it called the thing, how sure it is, why, and what that
 * does if it stands, with the means to agree or disagree. The accent is the kind of call, so a
 * list of them can be scanned: alarms in red, things set aside in amber and green.
 */
const props = defineProps<{ decision: Decision }>()
defineEmits<{ answered: [Decision] }>()

const look = computed(() => CLASSIFICATION[props.decision.kind])
const state = computed(() => REVIEW[props.decision.review])
const link = computed(() =>
  props.decision.subject === 'family'
    ? { name: 'family', params: { id: props.decision.id } }
    : { name: 'incident', params: { id: props.decision.id } },
)
const by = computed(() => {
  const { provider, model, decided_at: at } = props.decision
  const named = model ? ` (${model})` : ''
  return `${provider ?? 'The AI'}${named}, ${formatAgo(at)}`
})
const scope = computed(() => {
  const { subject, incidents } = props.decision
  if (subject === 'incident') return 'One incident'
  return `A kind of incident, ${formatCount(incidents)} ${incidents === 1 ? 'incident' : 'incidents'}`
})
</script>

<template>
  <v-card
    class="decision pa-4 pa-sm-5"
    :data-kind="decision.kind"
    :data-review="decision.review"
    data-test="review-card"
  >
    <div class="decision__chips">
      <v-chip
        :color="look.color"
        :prepend-icon="look.icon"
        :title="look.meaning"
        variant="tonal"
        data-test="review-kind"
      >
        {{ look.label }}
      </v-chip>
      <v-chip variant="outlined" data-test="review-confidence">
        {{ decision.confidence }}% sure
      </v-chip>
      <v-chip
        :color="state.color"
        :prepend-icon="state.icon"
        :title="state.meaning"
        variant="text"
        data-test="review-state"
      >
        {{ state.label }}
      </v-chip>
    </div>

    <h3 class="text-title-medium decision__title">
      <RouterLink :to="link" data-test="review-link">{{ decision.title }}</RouterLink>
    </h3>
    <p class="text-body-medium text-medium-emphasis" data-test="review-scope">{{ scope }}</p>

    <v-progress-linear
      :model-value="decision.confidence"
      :color="look.color"
      height="4"
      rounded
      :aria-label="`The AI is ${decision.confidence.toString()} percent sure`"
    />

    <p class="text-body-large" data-test="review-why">{{ decision.why }}</p>
    <p class="decision__effect text-body-large" data-test="review-effect">
      <b>{{ decision.counting ? 'It counts:' : 'If you agree:' }}</b>
      {{ decision.effect }}
    </p>
    <p class="text-body-medium text-medium-emphasis" data-test="review-by">{{ by }}</p>

    <ReviewAnswer
      :id="decision.id"
      :subject="decision.subject"
      :kind="decision.kind"
      :review="decision.review"
      :said="decision.reason"
      @answered="$emit('answered', $event)"
    />
  </v-card>
</template>

<style scoped>
.decision {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border-inline-start: 4px solid rgb(var(--v-theme-primary));
}

.decision[data-kind='compromise'],
.decision[data-kind='attack'] {
  border-inline-start-color: rgb(var(--v-theme-error));
}

.decision[data-kind='probe'] {
  border-inline-start-color: rgb(var(--v-theme-warning));
}

.decision[data-kind='noise'] {
  border-inline-start-color: rgb(var(--v-theme-success));
}

.decision p,
.decision h3 {
  margin: 0;
}

.decision__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.decision__title a {
  color: inherit;
  text-decoration-color: rgba(var(--v-theme-on-surface), 0.3);
  text-underline-offset: 0.2em;
  overflow-wrap: anywhere;
}
</style>
