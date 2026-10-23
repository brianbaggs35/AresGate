<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { computed } from 'vue'

import type { IntegrationSummary } from '@/api/integrations'
import StatusChip from '@/components/StatusChip.vue'
import { formatAgo, formatDateTime } from '@/format'
import { integrationIcon } from '@/integrations'

const props = defineProps<{ integration: IntegrationSummary }>()

const icon = computed(() => integrationIcon(props.integration.icon))
const notSetUp = computed(() => props.integration.status === 'not_connected')
</script>

<template>
  <!-- The whole card is the link to the integration's page, where it is connected and managed. -->
  <v-card
    :to="{ name: 'integration', params: { key: integration.key } }"
    class="integration-card pa-5"
    hover
    :data-test="`integration-${integration.key}`"
  >
    <div class="integration-card__head">
      <span class="integration-card__icon" aria-hidden="true">
        <component :is="icon" :size="26" />
      </span>
      <div class="integration-card__title">
        <h2 class="text-title-large" data-test="integration-name">{{ integration.name }}</h2>
        <StatusChip :status="integration.status" size="small" />
      </div>
    </div>

    <p class="text-body-medium text-medium-emphasis" data-test="integration-provides">
      {{ integration.provides }}
    </p>

    <ul
      v-if="integration.services.length"
      class="integration-card__services"
      aria-label="Services found"
      data-test="integration-services"
    >
      <li v-for="service in integration.services" :key="service.key">
        <v-chip size="small" variant="outlined" data-test="integration-service">
          {{ service.label }}
        </v-chip>
      </li>
    </ul>

    <div class="integration-card__foot text-body-medium">
      <span v-if="notSetUp" class="text-medium-emphasis" data-test="integration-last-call">
        Not set up yet
      </span>
      <span
        v-else-if="integration.last_success_at"
        class="text-medium-emphasis"
        data-test="integration-last-call"
      >
        Last successful call
        <time
          :datetime="integration.last_success_at"
          :title="formatDateTime(integration.last_success_at)"
          >{{ formatAgo(integration.last_success_at) }}</time
        >
      </span>
      <span v-else class="text-medium-emphasis" data-test="integration-last-call">
        No successful call yet
      </span>
      <span class="integration-card__action">
        {{ notSetUp ? 'Set up' : 'Manage' }}
        <ChevronRight :size="18" aria-hidden="true" />
      </span>
    </div>
  </v-card>
</template>

<style scoped>
.integration-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  height: 100%;
  text-decoration: none;
  transition: border-color 0.15s ease;
}

.integration-card:hover {
  border-color: rgb(var(--v-theme-primary));
}

.integration-card__head {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.integration-card__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.integration-card__title {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  min-width: 0;
}

.integration-card__title h2 {
  margin: 0;
}

.integration-card p {
  margin: 0;
}

.integration-card__services {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.integration-card__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: auto;
  padding-top: 0.75rem;
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.integration-card__action {
  display: inline-flex;
  align-items: center;
  gap: 0.125rem;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}
</style>
