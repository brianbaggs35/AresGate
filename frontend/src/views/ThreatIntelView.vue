<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatRulings from '@/components/ThreatRulings.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Threat intelligence: asking a service about an address, a domain or a web address. VirusTotal is
 * the one service for now. Its search is offered once its connection has been tested. Until then
 * the page says that a threat intelligence integration is needed, with a way to the Integrations
 * page, and nothing else in AresGate waits for it. Under the search is what AresGate knows: every
 * answer it has kept, which stays readable whether or not a service is connected now. Above that
 * is what the owner has ruled safe or suspicious, whatever the services made of it, which needs no
 * service either.
 */
const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
// Counts the answers this page has had, so the list of what is kept is read again after each.
const answers = ref(0)

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

    <ThreatLookup
      v-else-if="virustotal?.status === 'connected'"
      :pause="virustotal?.pause ?? null"
      @refused="load"
      @answered="answers += 1"
      @ruled="answers += 1"
    />

    <v-skeleton-loader
      v-else-if="!integrations"
      type="card"
      data-test="threat-intelligence-loading"
    />

    <SectionCard
      v-else
      title="Look up a threat"
      description="A threat intelligence integration answers the searches, once one is connected."
      data-test="threat-intelligence-setup"
    >
      <EmptyState
        title="No threat intelligence integration is connected"
        description="This page needs at least one threat intelligence integration connected, such as VirusTotal. Connect one on the Integrations page and test its connection. Then you can search here."
      >
        <v-btn
          :to="{ name: 'integrations' }"
          variant="tonal"
          data-test="threat-intelligence-set-up"
        >
          Go to Integrations
        </v-btn>
      </EmptyState>
    </SectionCard>

    <template v-if="integrations && !error">
      <ThreatRulings :version="answers" @changed="answers += 1" />
      <ThreatKnown :version="answers" @refused="load" @ruled="answers += 1" />
    </template>
  </AppPage>
</template>
