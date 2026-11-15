<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import type { Provider } from '@/api/threatIntel'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatRulings from '@/components/ThreatRulings.vue'
import { useSessionStore } from '@/stores/session'
import { PROVIDERS, providerOf } from '@/threatIntel'

/**
 * Threat intelligence: asking a service about an address, a domain or a web address. Each service
 * (VirusTotal, AlienVault OTX, GreyNoise) has a tab of its own, with its search and what AresGate
 * knows from it: every answer it has kept, which stays readable whether or not the service is
 * connected now. A service's search is offered once its connection has been tested. Until then its
 * tab says that it needs connecting, with a way to the Integrations page, and nothing else in
 * AresGate waits for it. Above the tabs is what the owner has ruled safe or suspicious, which
 * holds whichever service is asked, and needs no service either.
 */
const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
// Counts the answers this page has had, so the list of what is kept is read again after each.
const answers = ref(0)

// The service whose tab is open: the first of those connected once the list is read, else the
// first, and then whichever one the owner opens.
const chosen = ref<Provider | null>(null)
const service = computed(
  () =>
    chosen.value ??
    PROVIDERS.find((one) => connection(one.key)?.status === 'connected')?.key ??
    'virustotal',
)
const current = computed(() => providerOf(service.value))
const integration = computed(() => connection(service.value))

function connection(key: Provider) {
  return integrations.value?.find((item) => item.key === key)
}

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

    <v-skeleton-loader
      v-else-if="!integrations"
      type="card"
      data-test="threat-intelligence-loading"
    />

    <template v-else>
      <ThreatRulings :version="answers" @changed="answers += 1" />

      <v-tabs
        :model-value="service"
        aria-label="Threat intelligence service"
        class="threat-tabs"
        data-test="threat-tabs"
        @update:model-value="chosen = $event as Provider"
      >
        <v-tab
          v-for="one in PROVIDERS"
          :key="one.key"
          :value="one.key"
          :data-test="`threat-tab-${one.key}`"
        >
          {{ one.name }}
        </v-tab>
      </v-tabs>

      <ThreatLookup
        v-if="integration?.status === 'connected'"
        :key="`lookup-${service}`"
        :provider="service"
        :pause="integration.pause ?? null"
        @refused="load"
        @answered="answers += 1"
        @ruled="answers += 1"
      />

      <SectionCard
        v-else
        title="Look up a threat"
        :description="`${current.name} answers the searches, once it is connected.`"
        data-test="threat-intelligence-setup"
      >
        <EmptyState
          :title="`${current.name} is not connected`"
          :description="`Connect ${current.name} on the Integrations page and test its connection. Then you can search it here. Every answer it gave before stays below.`"
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

      <ThreatKnown
        :key="`known-${service}`"
        :provider="service"
        :version="answers"
        @refused="load"
        @ruled="answers += 1"
      />
    </template>
  </AppPage>
</template>

<style scoped>
.threat-tabs {
  margin-bottom: 0.5rem;
}
</style>
