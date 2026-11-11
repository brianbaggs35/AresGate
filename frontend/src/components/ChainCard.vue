<script setup lang="ts">
import { RouterLink } from 'vue-router'

import type { Chain } from '@/api/threats'
import SeverityChip from '@/components/SeverityChip.vue'
import { DEVICE_ICON, LINK, deviceTitle } from '@/chains'
import { formatAgo } from '@/format'

/**
 * An attack across two devices in a list: the device it went through, what happened in a sentence,
 * and whether the link between the steps was seen or only inferred. The card leads to the chain's
 * page, which draws the steps in order with the evidence behind each.
 */
defineProps<{ chain: Chain }>()
</script>

<template>
  <v-card hover class="chain-card" data-test="chain-card">
    <RouterLink
      :to="{ name: 'chain', params: { id: chain.id } }"
      class="chain-card__link"
      data-test="chain"
    >
      <div class="chain-card__top">
        <SeverityChip :severity="chain.severity" />
        <v-chip
          variant="outlined"
          :color="LINK[chain.confirmed ? 'confirmed' : 'inferred'].color"
          :prepend-icon="LINK[chain.confirmed ? 'confirmed' : 'inferred'].icon"
          data-test="chain-link"
        >
          {{ chain.confirmed ? 'Seen' : 'Inferred' }}
        </v-chip>
        <span class="chain-card__when text-body-medium text-medium-emphasis">
          Last seen
          <time :datetime="chain.last_seen_at">{{ formatAgo(chain.last_seen_at) }}</time>
        </span>
      </div>
      <h3 class="chain-card__title text-title-large">
        <v-icon :icon="DEVICE_ICON" size="22" aria-hidden="true" />
        <span data-test="chain-device">{{ deviceTitle(chain) }}</span>
      </h3>
      <p class="text-body-large chain-card__summary" data-test="chain-summary">
        {{ chain.summary }}
      </p>
    </RouterLink>
  </v-card>
</template>

<style scoped>
.chain-card {
  overflow: hidden;
  border-inline-start: 4px solid rgb(var(--v-theme-error));
}

.chain-card__link {
  display: block;
  padding: 1rem;
  color: inherit;
  text-decoration: none;
}

@media (min-width: 600px) {
  .chain-card__link {
    padding: 1.25rem;
  }
}

.chain-card__link:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.chain-card__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.chain-card__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.chain-card__when {
  margin-inline-start: auto;
}

.chain-card__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0 0.25rem;
  overflow-wrap: anywhere;
}

.chain-card__summary {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
