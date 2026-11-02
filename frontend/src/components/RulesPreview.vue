<script setup lang="ts">
import { useId } from 'vue'

import type { RulesPreview } from '@/api/alerts'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo } from '@/format'

/**
 * What a set of rules would have done in the last day: how many incidents they would have told
 * the owner of, why the rest were left out and the newest of those sent, each a link to the
 * incident. It is how the owner tunes the rules before saving them. It only shows what it is
 * given; asking is up to the dialog.
 */
defineProps<{
  /** The answer for the rules as they stand, or none before there is one. */
  preview: RulesPreview | null
  /** A newer answer is being worked out, so the one shown may be of earlier rules. */
  loading?: boolean
  /** Why there is no answer. */
  failure?: string | null
  /** The limit of messages an hour in the rules, to say what it would catch. */
  perHour: number
}>()

const titleId = useId()
</script>

<template>
  <section
    class="preview"
    :aria-labelledby="titleId"
    :aria-busy="loading ? 'true' : 'false'"
    data-test="rules-preview"
  >
    <h3 :id="titleId" class="text-title-medium mb-2">What these rules would have done</h3>
    <v-alert
      v-if="failure"
      type="warning"
      variant="tonal"
      density="compact"
      data-test="preview-failure"
    >
      {{ failure }}
    </v-alert>
    <div
      v-else-if="!preview"
      class="text-body-medium text-medium-emphasis"
      data-test="preview-wait"
    >
      Working out what these rules would have sent in the last day…
    </div>
    <div v-else :class="{ 'preview--stale': loading }" data-test="preview-answer">
      <p v-if="preview.considered === 0" class="text-body-large" data-test="preview-summary">
        No incidents were going on in the last {{ preview.hours }} hours, so there is nothing to
        show yet.
      </p>
      <p v-else-if="preview.would_send === 0" class="text-body-large" data-test="preview-summary">
        In the last {{ preview.hours }} hours these rules would have sent nothing.
        {{ preview.considered }}
        {{ preview.considered === 1 ? 'incident was' : 'incidents were' }}
        going on, and none met them.
      </p>
      <p v-else class="text-body-large" data-test="preview-summary">
        In the last {{ preview.hours }} hours these rules would have sent {{ preview.would_send }}
        {{ preview.would_send === 1 ? 'message' : 'messages' }}, out of {{ preview.considered }}
        {{ preview.considered === 1 ? 'incident' : 'incidents' }} going on.
      </p>

      <p v-if="preview.held > 0" class="text-body-medium" data-test="preview-held">
        {{ preview.held }} of them would have come in quiet hours and waited until those ended.
      </p>
      <p v-if="preview.over_limit > 0" class="text-body-medium" data-test="preview-limit">
        {{ preview.busiest_hour }} came in one hour. With at most {{ perHour }} messages an hour,
        {{ preview.over_limit }} would have been said in one summary instead.
      </p>
      <p
        v-if="preview.truncated"
        class="text-body-medium text-medium-emphasis"
        data-test="preview-truncated"
      >
        There were more incidents than could be looked at here, so this is the newest
        {{ preview.considered }}.
      </p>

      <template v-if="preview.left_out.length > 0">
        <h4 class="text-label-large mt-3">Left out</h4>
        <ul class="preview__list" data-test="preview-left-out">
          <li v-for="item in preview.left_out" :key="item.reason" class="text-body-medium">
            {{ item.text }}: <strong>{{ item.count }}</strong>
          </li>
        </ul>
      </template>

      <template v-if="preview.examples.length > 0">
        <h4 class="text-label-large mt-3">The newest that would have been sent</h4>
        <ul class="preview__list" data-test="preview-examples">
          <li v-for="item in preview.examples" :key="item.id" class="preview__example">
            <SeverityChip :severity="item.severity" size="small" />
            <router-link :to="`/incidents/${item.id.toString()}`" class="preview__title">
              {{ item.title }}
            </router-link>
            <span class="text-body-medium text-medium-emphasis">
              {{ item.confidence }}% sure · {{ formatAgo(item.last_seen_at) }}
            </span>
          </li>
        </ul>
      </template>
    </div>
  </section>
</template>

<style scoped>
.preview {
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  padding: 1rem;
}

.preview--stale {
  opacity: 0.6;
}

.preview p {
  margin: 0 0 0.5rem;
}

.preview__list {
  margin: 0.25rem 0 0;
  padding: 0;
  list-style: none;
}

.preview__list li {
  padding: 0.125rem 0;
}

.preview__example {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.preview__title {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
