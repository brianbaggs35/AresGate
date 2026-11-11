<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import { fetchChain, type ChainDetail } from '@/api/threats'
import AppPage from '@/components/AppPage.vue'
import ChainPath from '@/components/ChainPath.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { DEVICE_ICON, certainty, deviceTitle } from '@/chains'
import { formatAgo } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/**
 * One attack across two devices: an outside address got in by a flaw, and the device it got into
 * then called out. The page draws the steps in order with the evidence behind each, says which
 * links were seen and which are only inferred, and why the chain is a threat.
 */
const REFRESH_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const id = computed(() => Number(route.params.id))

const chain = ref<ChainDetail | null>(null)
const loadError = ref<string | null>(null)
/** The chain isn't there, which asking again won't change. */
const missing = ref(false)
const loading = ref(false)
let latest = 0

async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchChain(id.value))
    if (mine !== latest) return
    chain.value = found
    loadError.value = null
    missing.value = false
  } catch (error) {
    if (mine !== latest) return
    loadError.value = errorMessage(error)
    missing.value = error instanceof ApiError && error.status === 404
  } finally {
    if (mine === latest) loading.value = false
  }
}

onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="chain">
    <template v-if="chain">
      <PageHeader
        :title="`Attack on ${deviceTitle(chain)}`"
        :description="chain.summary"
        :back="{ to: { name: 'threats' }, label: 'Threats' }"
      >
        <template #icon>
          <v-icon :icon="DEVICE_ICON" size="32" />
        </template>
        <template #badge>
          <SeverityChip :severity="chain.severity" />
        </template>
      </PageHeader>

      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="chain-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>

      <v-alert
        :type="chain.confirmed ? 'error' : 'warning'"
        variant="tonal"
        :icon="false"
        data-test="chain-certainty"
      >
        <p class="text-title-medium">
          {{ chain.confirmed ? 'Seen, not guessed' : 'Part of this is inferred' }}
        </p>
        <p class="text-body-large">{{ certainty(chain) }}</p>
        <p class="text-body-medium">
          First seen
          <time :datetime="chain.first_seen_at">{{ formatAgo(chain.first_seen_at) }}</time
          >, last <time :datetime="chain.last_seen_at">{{ formatAgo(chain.last_seen_at) }}</time
          >.
        </p>
      </v-alert>

      <SectionCard
        title="The attack, step by step"
        description="In the order it happened, with what each program saw."
      >
        <ChainPath :chain="chain" />
      </SectionCard>

      <SectionCard
        v-if="chain.why.length"
        title="Why it is a threat"
        description="A chain is never set aside as background, whatever its steps look like alone."
        data-test="why-card"
      >
        <ul class="chain__why text-body-large">
          <li v-for="line in chain.why" :key="line" data-test="why">{{ line }}</li>
        </ul>
      </SectionCard>
    </template>
    <template v-else-if="loadError">
      <PageHeader title="Attack chain" :back="{ to: { name: 'threats' }, label: 'Threats' }" />
      <LoadError
        :message="missing ? `${loadError} It may have been removed.` : loadError"
        :can-retry="!missing"
        :loading="loading"
        data-test="chain-error"
        @retry="load()"
      />
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="chain-loading" />
  </AppPage>
</template>

<style scoped>
.chain__why {
  margin: 0;
  padding-inline-start: 1.25rem;
}

.chain :deep(p) {
  margin: 0;
}
</style>
