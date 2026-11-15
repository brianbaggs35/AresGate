<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import type { Provider, SubjectKind } from '@/api/threatIntel'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatCves from '@/components/ThreatCves.vue'
import ThreatDevices from '@/components/ThreatDevices.vue'
import ThreatKnown from '@/components/ThreatKnown.vue'
import ThreatLookup from '@/components/ThreatLookup.vue'
import ThreatRulings from '@/components/ThreatRulings.vue'
import { formatList } from '@/format'
import { useSessionStore } from '@/stores/session'
import { TYPES, providersFor, typeOf, type TypeKey } from '@/threatIntel'

/**
 * Threat intelligence, in a tab for each kind of it: IP addresses, domains, web addresses, CVEs
 * and devices. A tab is named for what the intelligence is about and not for the service that
 * gives it, so a service shows in every tab it has something for: VirusTotal in the first three,
 * AlienVault OTX in addresses and domains, GreyNoise in addresses. The first three tabs search
 * every connected service that answers about their kind, and list what AresGate has kept from all
 * of them, which stays readable whether or not a service is connected now. A service is searched
 * once its connection has been tested. Until then the tab says which services answer there and
 * need connecting, with a way to the Integrations page, and nothing else in AresGate waits for
 * them. The CVE tab lists what NVD says of the CVEs that incidents name, and the Devices tab what
 * Fingerbank made of each device; both are asked in the background, so they are read, not
 * searched. Above the tabs is what the owner has ruled safe or suspicious, which holds whichever
 * service is asked, and needs no service either.
 */
const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
// Counts the answers this page has had, so what is kept is read again after each.
const answers = ref(0)

const chosen = ref<TypeKey>('ip')
const type = computed(() => typeOf(chosen.value))
/** The kind of subject the open tab searches for, or null where it lists CVEs or devices. */
const subject = computed<SubjectKind | null>(() =>
  chosen.value === 'cve' || chosen.value === 'device' ? null : chosen.value,
)

function connection(key: Provider) {
  return integrations.value?.find((item) => item.key === key)
}

/** The services that answer about the open tab's kind, split by whether they can be searched. */
// Only read where a tab searches for a kind of subject.
const services = computed(() => providersFor(subject.value as SubjectKind))
const connected = computed(() =>
  services.value
    .filter((one) => connection(one.key)?.status === 'connected')
    .map((one) => ({ key: one.key, pause: connection(one.key)?.pause ?? null })),
)
const missing = computed(() =>
  services.value.filter((one) => connection(one.key)?.status !== 'connected').map((one) => one.key),
)

const names = computed(() => formatList(services.value.map((one) => one.name)))
const answering = computed(
  () => `${names.value} ${services.value.length === 1 ? 'answers' : 'answer'}`,
)

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
      description="What threat intelligence services say about the IP addresses, domains, web addresses, vulnerabilities and devices on your network, a tab for each. It adds context to how AresGate classifies threats and incidents. It is optional: without a service, AresGate works as it did before."
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
        :model-value="chosen"
        aria-label="Kind of threat intelligence"
        class="threat-tabs"
        show-arrows
        data-test="threat-tabs"
        @update:model-value="chosen = $event as TypeKey"
      >
        <v-tab
          v-for="one in TYPES"
          :key="one.key"
          :value="one.key"
          :prepend-icon="one.icon"
          :data-test="`threat-tab-${one.key}`"
        >
          {{ one.name }}
        </v-tab>
      </v-tabs>

      <template v-if="subject">
        <ThreatLookup
          v-if="connected.length"
          :key="`lookup-${subject}`"
          :kind="subject"
          :services="connected"
          :missing="missing"
          @refused="load"
          @answered="answers += 1"
          @ruled="answers += 1"
        />

        <SectionCard
          v-else
          :title="`Look up ${type.about}`"
          :description="`${answering} searches for ${type.about}, once connected.`"
          data-test="threat-intelligence-setup"
        >
          <EmptyState
            title="No service is connected for this"
            :description="`Connect ${services.length === 1 ? names : 'one of them'} on the Integrations page and test its connection. Then you can search here. Every answer a service gave before stays below.`"
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
          :key="`known-${subject}`"
          :kind="subject"
          :version="answers"
          @refused="load"
          @ruled="answers += 1"
        />
      </template>

      <ThreatCves v-else-if="chosen === 'cve'" :version="answers" />
      <ThreatDevices v-else :version="answers" />
    </template>
  </AppPage>
</template>

<style scoped>
.threat-tabs {
  margin-bottom: 0.5rem;
}
</style>
