<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Threat intelligence: asking a service about an address, a domain or a web address. VirusTotal is
 * the one service for now. Its search is offered once its connection has been tested. Until then
 * the page says what to set up, and nothing else in AresGate waits for it.
 */
const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const virustotal = computed(() => integrations.value?.find((item) => item.key === 'virustotal'))

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
      title="Threat intelligence"
      description="Ask a threat intelligence service about an IP address, a domain or a web address, and see what it reports. The answer adds context to how AresGate classifies threats and incidents. It is optional: without a service, AresGate works as it did before."
    />

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="threat-intelligence-retry"
      data-test="threat-intelligence-error"
      @retry="load"
    />

    <ThreatLookup v-else-if="virustotal?.status === 'connected'" />

    <v-skeleton-loader
      v-else-if="!integrations"
      type="card"
      data-test="threat-intelligence-loading"
    />

    <SectionCard
      v-else
      title="Look up a threat"
      description="VirusTotal answers the searches, once it is set up."
      data-test="threat-intelligence-setup"
    >
      <EmptyState
        title="VirusTotal isn't set up yet"
        description="Connect VirusTotal on its integration page, and test the connection. Then you can search here."
      >
        <v-btn
          :to="{ name: 'integration', params: { key: 'virustotal' } }"
          variant="tonal"
          data-test="threat-intelligence-set-up"
        >
          Set up VirusTotal
        </v-btn>
      </EmptyState>
    </SectionCard>
  </AppPage>
</template>
