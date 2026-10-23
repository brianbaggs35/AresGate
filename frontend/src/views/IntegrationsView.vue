<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import IntegrationCard from '@/components/IntegrationCard.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const isSetUp = ({ status }: IntegrationSummary) => status !== 'not_connected'

async function load() {
  loading.value = true
  error.value = null
  try {
    integrations.value = await session.call(fetchIntegrations)
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <v-container class="py-8" max-width="1000">
    <header class="d-flex flex-wrap align-center justify-space-between ga-3 mb-6">
      <div>
        <h1 class="text-headline-medium mb-1">Integrations</h1>
        <p class="text-body-large text-medium-emphasis">
          The systems AresGate watches your network through. It only reads from them: it never
          changes their settings.
        </p>
      </div>
      <p v-if="integrations" class="text-body-large" data-test="integrations-count">
        {{ integrations.filter(isSetUp).length }} of {{ integrations.length }} set up
      </p>
    </header>

    <v-alert v-if="error" type="error" variant="tonal" data-test="integrations-error">
      {{ error }}
      <template #append>
        <v-btn
          variant="text"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="integrations-retry"
          @click="load"
        >
          Try again
        </v-btn>
      </template>
    </v-alert>

    <v-row v-else-if="integrations" data-test="integrations-list">
      <v-col v-for="integration in integrations" :key="integration.key" cols="12" md="6">
        <IntegrationCard :integration="integration" />
      </v-col>
    </v-row>

    <v-row v-else data-test="integrations-loading">
      <v-col v-for="placeholder in 4" :key="placeholder" cols="12" md="6">
        <v-skeleton-loader type="card" />
      </v-col>
    </v-row>
  </v-container>
</template>
