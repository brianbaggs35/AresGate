<script setup lang="ts">
import { Globe, Laptop, ShieldAlert } from '@lucide/vue'
import { computed } from 'vue'

import type { ConversationEnd } from '@/api/incidents'
import { countryName, endTitle, flagOf, LOCATION, locationOf, portLine } from '@/evidence'
import { JUDGEMENT } from '@/threatIntel'

/**
 * One end of a conversation: who it is, where it is and what is known against it. A device on
 * your network is drawn quietly; an address on the internet that is on a blacklist, or that the
 * threat-intelligence service flags, is drawn in the color of a warning, with the reason written
 * out beside it, so the color is never the only thing that says so.
 */
const props = defineProps<{
  end: ConversationEnd
  /** Which end it is, to say so: the one that sent, or the one it was sent to. */
  role: 'client' | 'server'
}>()

const where = computed(() => locationOf(props.end))
const title = computed(() => endTitle(props.end))
const port = computed(() => portLine(props.end))
const country = computed(() => (props.end.country ? props.end.country : null))
const flagged = computed(
  () => props.end.blacklisted === true || ['malicious', 'suspicious'].includes(judgement.value),
)
const judgement = computed(() => props.end.reputation?.judgement ?? 'unknown')
const reputation = computed(() => {
  const found = props.end.reputation
  if (!found) return null
  const look = JUDGEMENT[found.judgement]
  const flags = found.malicious + found.suspicious
  const text =
    found.judgement === 'malicious' || found.judgement === 'suspicious'
      ? `${flags.toString()} of ${found.engines.toString()} engines flag it`
      : found.judgement === 'clean'
        ? `No engine of ${found.engines.toString()} flags it`
        : look.label
  return { look, text }
})
</script>

<template>
  <div
    class="end"
    :class="{ 'end--flagged': flagged, 'end--local': where === 'local' }"
    :data-test="`end-${role}`"
  >
    <span class="end__icon" aria-hidden="true">
      <v-icon :icon="where === 'local' ? Laptop : Globe" size="26" />
    </span>
    <div class="end__body">
      <p class="text-label-large text-medium-emphasis" data-test="end-role">
        {{ role === 'client' ? 'Sent from' : 'Sent to' }}
      </p>
      <p class="text-title-medium end__title" data-test="end-title">{{ title }}</p>
      <p class="text-body-medium text-medium-emphasis end__address" data-test="end-address">
        <span v-if="end.name">{{ end.address }}</span>
        <span v-if="port" data-test="end-port">
          <template v-if="end.name">, </template>port {{ port }}
        </span>
      </p>
      <div class="end__chips">
        <v-chip size="small" variant="tonal" data-test="end-location">
          {{ LOCATION[where] }}
        </v-chip>
        <v-chip v-if="country" size="small" variant="outlined" data-test="end-country">
          <span aria-hidden="true">{{ flagOf(country) }}&nbsp;</span>
          {{ countryName(country) }}
        </v-chip>
        <v-chip
          v-if="end.blacklisted"
          size="small"
          color="error"
          variant="tonal"
          :prepend-icon="ShieldAlert"
          data-test="end-blacklisted"
        >
          On a blacklist
        </v-chip>
        <v-chip
          v-if="reputation"
          size="small"
          :color="reputation.look.color"
          variant="tonal"
          :prepend-icon="reputation.look.icon"
          data-test="end-reputation"
        >
          {{ reputation.text }}
        </v-chip>
      </div>
      <p
        v-if="end.reputation?.owner"
        class="text-body-medium text-medium-emphasis"
        data-test="end-owner"
      >
        Belongs to {{ end.reputation.owner }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.end {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  min-width: 0;
  padding: 0.875rem 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.end--flagged {
  border-color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.07);
}

.end__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-secondary), 0.35);
  color: rgb(var(--v-theme-on-surface));
}

.end--local .end__icon {
  background: rgba(var(--v-theme-primary), 0.18);
}

.end--flagged .end__icon {
  background: rgba(var(--v-theme-error), 0.18);
}

.end__body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.end__body p {
  margin: 0;
}

.end__title,
.end__address {
  overflow-wrap: anywhere;
}

.end__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.25rem;
}
</style>
