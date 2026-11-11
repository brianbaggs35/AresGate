<script setup lang="ts">
import { ChevronRight, Trash2 } from '@lucide/vue'

import type { Trust } from '@/api/trust'
import { formatAgo } from '@/format'
import { LEVEL, appliedText } from '@/trust'

/**
 * One trust decision in the list: what is trusted, how much and why, what it has kept quiet, and
 * when it was last changed. The row opens the decision, where all of it can be changed; the
 * button beside it takes the decision back. On a phone the facts stack under what is trusted.
 */
defineProps<{ rule: Trust }>()
const emit = defineEmits<{ revoke: [] }>()
</script>

<template>
  <li class="trust-row" data-test="trust-row">
    <router-link
      :to="{ name: 'trust-decision', params: { id: rule.id } }"
      class="trust-row__link"
      data-test="trust-open"
    >
      <span class="trust-row__what">
        <span class="text-title-medium trust-row__about" data-test="trust-about">{{
          rule.about
        }}</span>
        <span
          v-if="rule.note"
          class="text-body-medium text-medium-emphasis trust-row__note"
          data-test="trust-note"
          >“{{ rule.note }}”</span
        >
      </span>
      <v-chip
        size="small"
        variant="tonal"
        :color="LEVEL[rule.verdict].color"
        :prepend-icon="LEVEL[rule.verdict].icon"
        class="trust-row__level"
        data-test="trust-level"
      >
        {{ LEVEL[rule.verdict].label }}
      </v-chip>
      <span class="text-body-medium trust-row__applied" data-test="trust-applied">
        {{ appliedText(rule) }}
        <template v-if="rule.last_hit_at"
          >, last
          <time :datetime="rule.last_hit_at">{{ formatAgo(rule.last_hit_at) }}</time></template
        >
      </span>
      <span class="text-body-medium text-medium-emphasis trust-row__changed">
        <time :datetime="rule.updated_at">{{ formatAgo(rule.updated_at) }}</time>
      </span>
      <v-icon :icon="ChevronRight" size="20" class="trust-row__go" aria-hidden="true" />
    </router-link>
    <v-btn
      icon
      variant="text"
      size="small"
      color="error"
      :aria-label="`Take back: ${rule.about}`"
      class="trust-row__delete"
      data-test="trust-revoke"
      @click="emit('revoke')"
    >
      <v-icon :icon="Trash2" />
    </v-btn>
  </li>
</template>

<style scoped>
.trust-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  border-block-start: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.trust-row:first-child {
  border-block-start: 0;
}

.trust-row__link {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    'what level'
    'applied applied'
    'changed changed';
  align-items: center;
  gap: 0.25rem 0.75rem;
  min-width: 0;
  min-height: 44px;
  padding: 0.875rem 0.5rem;
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
}

.trust-row__link:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.trust-row__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.trust-row__what {
  grid-area: what;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.trust-row__about,
.trust-row__note {
  overflow-wrap: anywhere;
}

.trust-row__level {
  grid-area: level;
}

.trust-row__applied {
  grid-area: applied;
}

.trust-row__changed {
  grid-area: changed;
}

.trust-row__go {
  display: none;
}

/* Wide enough, the facts sit in columns, so that a list of them can be read down. */
@media (min-width: 960px) {
  .trust-row__link {
    grid-template-columns: minmax(0, 3fr) 8.5rem minmax(0, 2.5fr) 6.5rem 1.25rem;
    grid-template-areas: 'what level applied changed go';
  }

  .trust-row__go {
    display: inline-flex;
    color: rgba(var(--v-theme-on-surface), 0.6);
  }
}
</style>
