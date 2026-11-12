<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { fetchAsset, type AssetDetail } from '@/api/assets'
import { ApiError, errorMessage } from '@/api/client'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import AppPage from '@/components/AppPage.vue'
import AssetClassify from '@/components/AssetClassify.vue'
import AssetEvents from '@/components/AssetEvents.vue'
import AssetKindChip from '@/components/AssetKindChip.vue'
import AssetPeers from '@/components/AssetPeers.vue'
import AssetSources from '@/components/AssetSources.vue'
import AssetStatusChip from '@/components/AssetStatusChip.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import StatTile from '@/components/StatTile.vue'
import { formatAgo, formatBytes, formatCount, formatDateTime } from '@/format'
import { STATUS as INCIDENT_STATUS } from '@/incidents'
import { chartOf, descriptionOf, eventsNoteOf, scopeOfVerdict, STATUS } from '@/inventory'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'
import { VERDICT } from '@/verdicts'

/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

/**
 * One asset's page: what it is, how it has been on the network, the traffic ntopng measured for it,
 * the events its addresses were in, what it talked to, and the incidents and verdicts about it.
 */
const session = useSessionStore()
const route = useRoute()

const key = computed(() => String(route.params.key))
const data = ref<AssetDetail | null>(null)
const missing = ref(false)
const loadError = ref<string | null>(null)
const loading = ref(false)
const range = ref<'24h' | '7d'>('24h')

/**
 * Fetches the page. A refresh in the background leaves what is on screen as it is, and an answer
 * for an asset the page has moved on from is dropped.
 */
async function load(quiet = false) {
  const asked = key.value
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchAsset(asked))
    if (asked !== key.value) return
    data.value = found
    missing.value = false
    loadError.value = null
  } catch (error) {
    if (asked !== key.value) return
    if (error instanceof ApiError && error.status === 404) {
      data.value = null
      missing.value = true
    } else if (!quiet || !data.value) {
      loadError.value = errorMessage(error)
    }
  } finally {
    if (asked === key.value) loading.value = false
  }
}

/** Shows the traffic of the last day by the hour, or of the last week by the day. */
function pick(next: unknown) {
  range.value = next === '7d' ? '7d' : '24h'
}

watch(key, () => {
  data.value = null
  missing.value = false
  loadError.value = null
  void load()
})

onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide">
    <LoadError
      v-if="loadError"
      :message="loadError"
      :loading="loading"
      retry-test-id="asset-retry"
      data-test="asset-error"
      @retry="load()"
    />

    <template v-else-if="data">
      <PageHeader
        :title="data.asset.name"
        :description="descriptionOf(data.asset)"
        :back="{ to: { name: 'assets' }, label: 'Assets' }"
      >
        <template #badge>
          <AssetStatusChip :status="data.asset.status" />
          <AssetKindChip
            v-if="data.asset.profile"
            :kind="data.asset.profile.kind"
            :label="data.asset.profile.kind_label"
          />
        </template>
      </PageHeader>

      <p v-if="data.asset.profile?.purpose" class="text-body-large" data-test="asset-purpose-line">
        {{ data.asset.profile.purpose }}
      </p>

      <AssetClassify :asset="data.asset" @changed="load(true)" />

      <div class="tiles">
        <StatTile
          label="Last listed"
          :value="formatAgo(data.asset.last_seen_at)"
          :hint="STATUS[data.asset.status].label"
          data-test="asset-tile-listed"
        />
        <StatTile
          label="Sent, last day"
          :value="data.traffic.measured ? formatBytes(data.traffic.sent_day) : '–'"
          :hint="data.traffic.measured ? 'Measured by ntopng' : 'Nothing measured yet'"
          data-test="asset-tile-sent"
        />
        <StatTile
          label="Received, last day"
          :value="data.traffic.measured ? formatBytes(data.traffic.received_day) : '–'"
          :hint="data.traffic.measured ? 'Measured by ntopng' : 'Nothing measured yet'"
          data-test="asset-tile-received"
        />
        <StatTile
          label="Events, last day"
          :value="formatCount(data.events_day)"
          :hint="`${formatCount(data.events_week)} in the last week`"
          data-test="asset-tile-events"
        />
      </div>

      <v-card class="pa-5 pa-sm-6">
        <v-btn-toggle
          :model-value="range"
          mandatory
          density="comfortable"
          variant="outlined"
          divided
          aria-label="How far back to look"
          class="windows"
          data-test="asset-window"
          @update:model-value="pick"
        >
          <v-btn value="24h" :aria-pressed="range === '24h'">24 hours</v-btn>
          <v-btn value="7d" :aria-pressed="range === '7d'">7 days</v-btn>
        </v-btn-toggle>
        <TimeSeriesChart
          v-bind="chartOf(data.traffic, range)"
          title="Traffic"
          caption="What ntopng counted going to and from it, in each stretch of time."
          :format="formatBytes"
          :loading="loading"
          empty-title="No traffic measured yet"
          empty-description="ntopng measures the traffic of the devices it can see. Once it has read this one, its traffic is charted here."
          data-test="asset-chart"
        />
      </v-card>

      <section v-if="data.networks.length" class="section" aria-labelledby="networks-title">
        <h2 id="networks-title" class="text-title-large">On</h2>
        <ul class="chips">
          <li v-for="network in data.networks" :key="network.id">
            <v-chip variant="outlined" data-test="asset-network">{{ network.name }}</v-chip>
          </li>
        </ul>
      </section>

      <section class="section" aria-labelledby="addresses-title" data-test="asset-addresses">
        <h2 id="addresses-title" class="text-title-large">Addresses</h2>
        <p
          v-if="data.addresses.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="asset-no-addresses"
        >
          No address is listed for it.
        </p>
        <v-card v-else class="rows">
          <div
            v-for="item in data.addresses"
            :key="item.address"
            class="row"
            data-test="asset-address"
          >
            <span class="mono">{{ item.address }}</span>
            <v-chip
              size="small"
              variant="tonal"
              :color="item.current ? 'success' : undefined"
              data-test="asset-address-now"
            >
              {{ item.current ? 'Now' : 'Before' }}
            </v-chip>
            <span class="text-body-medium text-medium-emphasis">
              First seen
              <time :datetime="item.first_seen_at" :title="formatDateTime(item.first_seen_at)">{{
                formatAgo(item.first_seen_at)
              }}</time
              >, last seen
              <time :datetime="item.last_seen_at" :title="formatDateTime(item.last_seen_at)">{{
                formatAgo(item.last_seen_at)
              }}</time>
            </span>
          </div>
        </v-card>
      </section>

      <section class="section" aria-labelledby="sources-title" data-test="asset-listed-by">
        <h2 id="sources-title" class="text-title-large">Listed by</h2>
        <AssetSources :asset="data.asset" />
      </section>

      <section class="section" aria-labelledby="events-title" data-test="asset-events-section">
        <h2 id="events-title" class="text-title-large">Events</h2>
        <p class="text-body-medium text-medium-emphasis" data-test="asset-events-note">
          {{ eventsNoteOf(data.events_week) }}
        </p>
        <AssetEvents v-if="data.events.length" :events="data.events" />
      </section>

      <section class="section" aria-labelledby="peers-title" data-test="asset-peers">
        <h2 id="peers-title" class="text-title-large">Traffic with</h2>
        <AssetPeers :talks-to="data.talks_to" :contacted-by="data.contacted_by" />
      </section>

      <section class="section" aria-labelledby="incidents-title" data-test="asset-incidents">
        <h2 id="incidents-title" class="text-title-large">Incidents</h2>
        <p
          v-if="data.incidents.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="asset-no-incidents"
        >
          None of its addresses is in an incident.
        </p>
        <v-card v-else class="rows">
          <router-link
            v-for="item in data.incidents"
            :key="item.id"
            class="row row--link"
            :to="{ name: 'incident', params: { id: item.id } }"
            data-test="asset-incident"
          >
            <SeverityChip :severity="item.severity" />
            <span class="row__title">{{ item.title }}</span>
            <span class="text-body-medium text-medium-emphasis">
              {{ INCIDENT_STATUS[item.status].label }}, {{ formatAgo(item.last_seen_at) }}
            </span>
          </router-link>
        </v-card>
      </section>

      <section class="section" aria-labelledby="verdicts-title" data-test="asset-verdicts">
        <h2 id="verdicts-title" class="text-title-large">Verdicts</h2>
        <p
          v-if="data.verdicts.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="asset-no-verdicts"
        >
          You have not given a verdict about it.
        </p>
        <v-card v-else class="rows">
          <div v-for="item in data.verdicts" :key="item.id" class="row" data-test="asset-verdict">
            <v-chip
              :color="VERDICT[item.verdict].color"
              :prepend-icon="VERDICT[item.verdict].icon"
              size="small"
              variant="tonal"
            >
              {{ VERDICT[item.verdict].label }}
            </v-chip>
            <span class="row__title">{{ scopeOfVerdict(item) }}</span>
            <span class="text-body-medium text-medium-emphasis">
              {{ formatAgo(item.created_at) }}
            </span>
          </div>
        </v-card>
      </section>
    </template>

    <template v-else-if="missing">
      <PageHeader title="Assets" :back="{ to: { name: 'assets' }, label: 'Assets' }" />
      <EmptyState
        title="That asset isn't there"
        description="It may be on the Internet side of the network, which is not counted as an asset, or it may have left the list. The Assets page lists the ones on the network."
        data-test="asset-missing"
      />
    </template>

    <v-skeleton-loader v-else type="heading, card, card" data-test="asset-loading" />
  </AppPage>
</template>

<style scoped>
.windows {
  align-self: flex-start;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.75rem;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section h2,
.section p {
  margin: 0;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rows {
  padding: 0.25rem 1.25rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.75rem 0;
  color: inherit;
  text-decoration: none;
}

.row + .row,
.row--link + .row--link {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.row--link:hover,
.row--link:focus-visible {
  text-decoration: underline;
}

.row__title {
  min-width: 0;
  flex: 1 1 12rem;
  overflow-wrap: anywhere;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}
</style>
