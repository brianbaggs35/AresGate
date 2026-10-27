<script setup lang="ts">
import { computed, useId } from 'vue'

import CopyButton from '@/components/CopyButton.vue'
import { formatBytes } from '@/format'
import { jsonTokens, rawText } from '@/logs'

/**
 * What an integration sent about an event, as it was received (secrets and oversize parts are
 * already taken out when it is stored), pretty-printed and coloured by what each part is. It
 * wraps rather than scrolls, so all of it can be read and selected without a scroll bar, and it
 * can be copied whole.
 */
const props = defineProps<{
  /** The record, or null where none was kept for the event. */
  raw: Record<string, unknown> | null
}>()

const headingId = useId()
// Read only where there is a record to show.
const text = computed(() => rawText(props.raw as Record<string, unknown>))
const tokens = computed(() => jsonTokens(text.value))
</script>

<template>
  <section class="raw" :aria-labelledby="headingId" data-test="raw-record">
    <div class="raw__head">
      <h3 :id="headingId" class="text-title-small">Record as received</h3>
      <span v-if="raw" class="text-body-medium text-medium-emphasis" data-test="raw-size">
        {{ formatBytes(text.length) }}
      </span>
      <CopyButton v-if="raw" class="raw__copy" :text="text" label="the record" />
    </div>
    <code v-if="raw" class="raw__text" data-test="raw-text"
      ><span
        v-for="(token, index) in tokens"
        :key="index"
        :class="token.kind === 'plain' ? undefined : `raw__${token.kind}`"
        >{{ token.text }}</span
      ></code
    >
    <p v-else class="text-body-medium text-medium-emphasis" data-test="raw-none">
      The integration did not send a record of this event, or it was not kept.
    </p>
  </section>
</template>

<style scoped>
.raw__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.raw__head h3 {
  margin: 0;
}

.raw__copy {
  margin-inline-start: auto;
}

.raw__text {
  display: block;
  margin-top: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  tab-size: 2;
}

/* The colors lean toward the text color, so they read as well on a dark theme as a light one. */
.raw__key {
  color: color-mix(in srgb, rgb(var(--v-theme-primary)) 75%, rgb(var(--v-theme-on-surface)));
}

.raw__string {
  color: color-mix(in srgb, rgb(var(--v-theme-success)) 60%, rgb(var(--v-theme-on-surface)));
}

.raw__number {
  color: color-mix(in srgb, rgb(var(--v-theme-warning)) 55%, rgb(var(--v-theme-on-surface)));
}

.raw__literal {
  color: color-mix(in srgb, rgb(var(--v-theme-info)) 65%, rgb(var(--v-theme-on-surface)));
}
</style>
