<script setup lang="ts">
import { Gavel, Globe, Laptop, Network, ShieldAlert } from '@lucide/vue'
import { computed, ref } from 'vue'

import type { ConversationEnd, Reputation } from '@/api/incidents'
import ThreatRulingDialog from '@/components/ThreatRulingDialog.vue'
import { countryName, endTitle, flagOf, LOCATION, locationOf, portLine } from '@/evidence'
import { JUDGEMENT, RULING } from '@/threatIntel'

/**
 * One end of a conversation: who it is, where it is and what is known against it. A device on
 * your network is drawn quietly; an address on the internet that is on a blacklist, or that the
 * threat-intelligence service flags, is drawn in the color of a warning, with the reason written
 * out beside it, so the color is never the only thing that says so. An address on the internet can
 * be ruled on from here: where the owner says it is safe, or suspicious, that is what it is drawn
 * as, with what the service said beside it. `ruled` says that the owner ruled on it, or took it back.
 */
const props = defineProps<{
  end: ConversationEnd
  /** Which end it is, to say so: the one that sent, or the one it was sent to. */
  side: 'client' | 'server'
}>()
const emit = defineEmits<{ ruled: [] }>()

const ruling = computed(() => props.end.reputation?.ruling ?? null)
const ruleOpen = ref(false)
const where = computed(() => locationOf(props.end))
const title = computed(() => endTitle(props.end))
const port = computed(() => portLine(props.end))
const country = computed(() => (props.end.country ? props.end.country : null))
// What the owner says stands over what a program or a service flagged.
const flagged = computed(() =>
  ruling.value === 'safe'
    ? false
    : props.end.blacklisted === true || ['malicious', 'suspicious'].includes(judgement.value),
)
const judgement = computed(() => props.end.reputation?.judgement ?? 'unknown')
/** What the engines made of an address, in words: what the service said, whatever was ruled. */
function engineWords(found: Reputation): string {
  const flags = found.malicious + found.suspicious
  if (found.reported === 'malicious' || found.reported === 'suspicious') {
    return `${flags.toString()} of ${found.engines.toString()} engines flag it`
  }
  if (found.reported === 'clean') return `No engine of ${found.engines.toString()} flags it`
  return JUDGEMENT[found.reported].label
}

const engines = computed(() => {
  const found = props.end.reputation
  if (!found) return null
  return { look: JUDGEMENT[found.reported], text: engineWords(found) }
})
/** What the owner ruled, in words, with the same color a judgement of it would have. */
const ruled = computed(() => (ruling.value ? RULING[ruling.value] : null))
/** Whether the address can be ruled on: only what is on the internet, which a service can judge. */
const ruleable = computed(() => where.value === 'remote')
const heard = computed(() =>
  engines.value ? `VirusTotal said: ${engines.value.text.toLowerCase()}.` : null,
)
const current = computed(() =>
  ruling.value ? { verdict: ruling.value, note: props.end.reputation?.ruling_note ?? null } : null,
)
</script>

<template>
  <div
    class="end"
    :class="{ 'end--flagged': flagged, 'end--local': where === 'local' }"
    :data-test="`end-${side}`"
  >
    <span class="end__icon" aria-hidden="true">
      <v-icon :icon="where === 'local' ? Laptop : Globe" size="26" />
    </span>
    <div class="end__body">
      <p class="text-label-large text-medium-emphasis" data-test="end-role">
        {{ side === 'client' ? 'Sent from' : 'Sent to' }}
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
        <v-chip
          v-if="end.name_from === 'dns'"
          size="small"
          variant="outlined"
          :prepend-icon="Network"
          title="The name its owner gave the address, found by looking it up (reverse DNS)"
          data-test="end-dns"
        >
          Name from DNS
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
          v-if="ruled"
          size="small"
          :color="ruled.color"
          variant="tonal"
          :prepend-icon="ruled.icon"
          data-test="end-ruling"
        >
          {{ ruled.label }}
        </v-chip>
        <v-chip
          v-if="engines"
          size="small"
          :color="ruled ? undefined : engines.look.color"
          :variant="ruled ? 'outlined' : 'tonal'"
          :prepend-icon="engines.look.icon"
          data-test="end-reputation"
        >
          {{ engines.text }}
        </v-chip>
      </div>
      <p
        v-if="end.reputation?.owner"
        class="text-body-medium text-medium-emphasis"
        data-test="end-owner"
      >
        Belongs to {{ end.reputation.owner }}
      </p>
      <p
        v-if="end.reputation?.ruling_note"
        class="text-body-medium end__why"
        data-test="end-ruling-note"
      >
        “{{ end.reputation.ruling_note }}”
      </p>
      <div v-if="ruleable" class="end__rule">
        <v-btn
          variant="text"
          size="small"
          density="comfortable"
          :prepend-icon="Gavel"
          :aria-label="`${ruling ? 'Change my ruling of' : 'Rule on it for'} ${end.address}`"
          data-test="end-rule"
          @click="ruleOpen = true"
        >
          {{ ruling ? 'Change my ruling' : 'Rule on it' }}
        </v-btn>
      </div>
      <ThreatRulingDialog
        v-if="ruleable"
        v-model="ruleOpen"
        :subject="end.address"
        :ruling="current"
        :heard="heard"
        @changed="emit('ruled')"
      />
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

.end__why {
  font-style: italic;
}

.end__rule {
  margin-inline-start: -0.5rem;
}

.end__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.25rem;
}
</style>
