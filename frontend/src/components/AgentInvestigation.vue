<script setup lang="ts">
import { computed } from 'vue'

import type { Moment } from '@/api/agents'
import { MOMENT_LABEL } from '@/agents'
import { formatDateTime } from '@/format'

/**
 * How a conclusion was reached, in the order it happened: which agent looked at what, whom it
 * asked, what it concluded and what you decided. It is made of what the agents and you already
 * left, so reading it changes nothing. What an agent wrote is shown as text.
 */
const props = defineProps<{
  moments: readonly Moment[]
  /** What to say when nothing has happened yet. */
  empty?: string
}>()

const message = computed(() => props.empty ?? 'Nothing is recorded about this yet.')
</script>

<template>
  <div class="investigation" data-test="investigation">
    <p
      v-if="!moments.length"
      class="text-body-large text-medium-emphasis"
      data-test="investigation-none"
    >
      {{ message }}
    </p>
    <ol v-else class="investigation__list">
      <li
        v-for="(moment, at) in moments"
        :key="at"
        class="moment"
        :class="`moment--${moment.kind}`"
        data-test="moment"
      >
        <span class="moment__marker" aria-hidden="true" />
        <div class="moment__body">
          <div class="moment__head text-label-large">
            <span data-test="moment-agent">{{ moment.agent }}</span>
            <span class="text-medium-emphasis" data-test="moment-kind">{{
              MOMENT_LABEL[moment.kind]
            }}</span>
            <span class="text-label-small text-medium-emphasis moment__when">{{
              formatDateTime(moment.at)
            }}</span>
          </div>
          <p class="text-body-large moment__title" data-test="moment-title">{{ moment.title }}</p>
          <p
            v-if="moment.detail"
            class="text-body-medium text-medium-emphasis moment__detail"
            data-test="moment-detail"
          >
            {{ moment.detail }}
          </p>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.investigation p {
  margin: 0;
}

.investigation__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.moment {
  display: grid;
  grid-template-columns: 0.75rem minmax(0, 1fr);
  gap: 0.75rem;
}

.moment__marker {
  width: 0.75rem;
  height: 0.75rem;
  margin-top: 0.375rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.moment--concluded .moment__marker,
.moment--decided .moment__marker {
  background: rgb(var(--v-theme-primary));
}

.moment--handoff .moment__marker,
.moment--asked_by .moment__marker,
.moment--planned .moment__marker {
  background: rgb(var(--v-theme-info));
}

.moment__body {
  min-width: 0;
}

.moment__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.125rem 0.5rem;
}

.moment__when {
  margin-inline-start: auto;
}

.moment__title,
.moment__detail {
  overflow-wrap: anywhere;
}
</style>
