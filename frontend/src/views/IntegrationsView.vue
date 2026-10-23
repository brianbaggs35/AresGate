<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import AppPage from '@/components/AppPage.vue'
import IntegrationCard from '@/components/IntegrationCard.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
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
  <AppPage>
    <PageHeader
      title="Integrations"
      description="The systems AresGate watches your network through. It only reads from them: it never changes their settings."
    >
      <template v-if="integrations" #actions>
        <p class="text-body-large" data-test="integrations-count">
          {{ integrations.filter(isSetUp).length }} of {{ integrations.length }} set up
        </p>
      </template>
    </PageHeader>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="integrations-retry"
      data-test="integrations-error"
      @retry="load"
    />

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
  </AppPage>
</template>
