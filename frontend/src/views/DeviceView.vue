<script setup lang="ts">
import { Siren } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import { fetchDevice, type DeviceDetail } from '@/api/devices'
import AppPage from '@/components/AppPage.vue'
import AssetEvents from '@/components/AssetEvents.vue'
import AssetIdentity from '@/components/AssetIdentity.vue'
import DeviceConnections from '@/components/DeviceConnections.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import StatTile from '@/components/StatTile.vue'
import { nameOf, SCOPE } from '@/devices'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { STATUS as INCIDENT_STATUS } from '@/incidents'
import { eventsNoteOf } from '@/inventory'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'
import { JUDGEMENT, RULING } from '@/threatIntel'

/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

/**
 * One device's page: whose it is, how many connections were made to it and by it, what it
 * connected with and over which ports, the events it was in, the incidents and kinds of threat it
 * belongs to, and what threat intelligence and the fingerprinting service kept of it.
 */
const session = useSessionStore()
const route = useRoute()

const address = computed(() => String(route.params.address))
const data = ref<DeviceDetail | null>(null)
const missing = ref(false)
const loadError = ref<string | null>(null)
const loading = ref(false)

/**
 * Fetches the page. A refresh in the background leaves what is on screen as it is, and an answer
 * for a device the page has moved on from is dropped.
 */
async function load(quiet = false) {
  const asked = address.value
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchDevice(asked))
    if (asked !== address.value) return
    data.value = found
    missing.value = false
    loadError.value = null
  } catch (error) {
    if (asked !== address.value) return
    if (error instanceof ApiError && error.status === 404) {
      data.value = null
      missing.value = true
    } else if (!quiet || !data.value) {
      loadError.value = errorMessage(error)
    }
  } finally {
    if (asked === address.value) loading.value = false
  }
}

watch(address, () => {
  data.value = null
  missing.value = false
  loadError.value = null
  void load()
})

/** What the page says under the address: what it is called, and whose it is. */
const description = computed(() => {
  const { device } = data.value as DeviceDetail
  return [nameOf(device), SCOPE[device.scope].label].filter(Boolean).join(' · ')
})

/** How many engines flagged the address, of how many gave a verdict. */
const flagged = computed(() => {
  const { standing } = (data.value as DeviceDetail).device
  if (!standing || standing.reported === 'unknown') return ''
  return `${formatCount(standing.malicious + standing.suspicious)} of ${formatCount(standing.engines)} engines flagged it`
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
      retry-test-id="device-retry"
      data-test="device-error"
      @retry="load()"
    />

    <template v-else-if="data">
      <PageHeader
        :title="data.device.address"
        :description="description"
        :back="{ to: { name: 'devices' }, label: 'Devices' }"
      >
        <template #badge>
          <v-chip variant="tonal" size="small" data-test="device-scope">
            <v-icon :icon="SCOPE[data.device.scope].icon" size="16" start aria-hidden="true" />
            {{ SCOPE[data.device.scope].label }}
          </v-chip>
          <v-chip
            v-if="data.device.standing"
            :color="JUDGEMENT[data.device.standing.judgement].color"
            :prepend-icon="JUDGEMENT[data.device.standing.judgement].icon"
            variant="tonal"
            size="small"
            data-test="device-standing"
          >
            {{ JUDGEMENT[data.device.standing.judgement].short }}
          </v-chip>
          <v-chip
            v-if="data.device.incidents"
            :prepend-icon="Siren"
            color="error"
            variant="tonal"
            size="small"
            data-test="device-incidents"
          >
            In {{ formatCount(data.device.incidents.count) }}
            {{ data.device.incidents.count === 1 ? 'incident' : 'incidents' }}
          </v-chip>
        </template>
      </PageHeader>

      <div class="tiles">
        <StatTile
          label="Connected to it"
          :value="formatCount(data.device.incoming)"
          hint="Incoming, last 7 days"
          data-test="device-tile-incoming"
        />
        <StatTile
          label="Connected out"
          :value="formatCount(data.device.outgoing)"
          hint="Outgoing, last 7 days"
          data-test="device-tile-outgoing"
        />
        <StatTile
          label="Last seen"
          :value="formatAgo(data.device.last_seen_at)"
          :hint="formatDateTime(data.device.last_seen_at)"
          data-test="device-tile-seen"
        />
        <StatTile
          label="Events, last day"
          :value="formatCount(data.events_day)"
          :hint="eventsNoteOf(data.events_week)"
          data-test="device-tile-events"
        />
      </div>

      <section class="section" aria-labelledby="connections-title" data-test="device-connections">
        <h2 id="connections-title" class="text-title-large">Connections</h2>
        <p
          v-if="data.connections.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="device-no-connections"
        >
          No connection was reported in the last 7 days.
        </p>
        <v-card v-else class="pa-4 pa-sm-5">
          <DeviceConnections :connections="data.connections" />
        </v-card>
      </section>

      <section
        v-if="data.device.asset"
        class="section"
        aria-labelledby="asset-title"
        data-test="device-asset-section"
      >
        <h2 id="asset-title" class="text-title-large">Your device</h2>
        <v-card class="pa-4 pa-sm-5 asset">
          <p class="text-body-large">
            <router-link
              :to="{ name: 'asset', params: { key: data.device.asset.key } }"
              data-test="device-asset-link"
            >
              {{ data.device.asset.name }}
            </router-link>
            <span v-if="data.device.asset.vendor" class="text-medium-emphasis">
              · {{ data.device.asset.vendor }}
            </span>
            <span v-if="data.device.asset.mac" class="text-medium-emphasis mono">
              · {{ data.device.asset.mac }}
            </span>
          </p>
          <p
            v-if="data.device.asset.profile"
            class="text-body-medium text-medium-emphasis"
            data-test="device-asset-kind"
          >
            {{ data.device.asset.profile.kind_label }}
            <template v-if="data.device.asset.profile.purpose">
              · {{ data.device.asset.profile.purpose }}
            </template>
          </p>
        </v-card>
        <AssetIdentity
          v-if="data.device.asset.identity"
          :identity="data.device.asset.identity"
          data-test="device-identity"
        />
      </section>

      <section
        v-if="data.device.standing"
        class="section"
        aria-labelledby="standing-title"
        data-test="device-standing-section"
      >
        <h2 id="standing-title" class="text-title-large">What threat intelligence says</h2>
        <v-card class="pa-4 pa-sm-5 asset">
          <p class="text-body-large" data-test="device-standing-text">
            {{ JUDGEMENT[data.device.standing.judgement].label }}
          </p>
          <p v-if="flagged" class="text-body-medium text-medium-emphasis">{{ flagged }}</p>
          <p
            v-if="data.device.standing.owner || data.device.standing.country"
            class="text-body-medium text-medium-emphasis"
          >
            {{
              [data.device.standing.owner, data.device.standing.country].filter(Boolean).join(', ')
            }}
          </p>
          <p v-if="data.device.standing.ruling" class="text-body-medium" data-test="device-ruling">
            You ruled it {{ RULING[data.device.standing.ruling].label.toLowerCase() }}.
            <template v-if="data.device.standing.ruling_note">
              {{ data.device.standing.ruling_note }}
            </template>
          </p>
          <p class="text-body-small text-medium-emphasis">
            Checked {{ formatAgo(data.device.standing.checked_at) }}.
          </p>
        </v-card>
      </section>

      <section class="section" aria-labelledby="incidents-title" data-test="device-incidents-list">
        <h2 id="incidents-title" class="text-title-large">Incidents and threats</h2>
        <p
          v-if="data.incidents.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="device-no-incidents"
        >
          It is not in an incident.
        </p>
        <v-card v-else class="rows">
          <div
            v-for="item in data.incidents"
            :key="item.id"
            class="row"
            data-test="device-incident"
          >
            <SeverityChip :severity="item.severity" />
            <router-link
              class="row__title"
              :to="{ name: 'incident', params: { id: item.id } }"
              data-test="device-incident-link"
            >
              {{ item.title }}
            </router-link>
            <span class="text-body-medium text-medium-emphasis">
              {{ INCIDENT_STATUS[item.status].label }}, {{ formatAgo(item.last_seen_at) }}
            </span>
            <span class="row__links text-body-medium">
              <router-link
                v-if="item.family_id !== null"
                :to="{ name: 'family', params: { id: item.family_id } }"
                data-test="device-family-link"
              >
                {{ item.family_label ?? 'Kind of threat' }}
              </router-link>
              <router-link
                v-if="item.chain_id !== null"
                :to="{ name: 'chain', params: { id: item.chain_id } }"
                data-test="device-chain-link"
              >
                Attack chain
              </router-link>
            </span>
          </div>
        </v-card>
      </section>

      <section class="section" aria-labelledby="events-title" data-test="device-events-section">
        <h2 id="events-title" class="text-title-large">Events</h2>
        <p
          v-if="data.events.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="device-no-events"
        >
          No event in the last 7 days.
        </p>
        <v-card v-else class="pa-4 pa-sm-5">
          <AssetEvents :events="data.events" />
        </v-card>
      </section>
    </template>

    <template v-else-if="missing">
      <PageHeader title="Devices" :back="{ to: { name: 'devices' }, label: 'Devices' }" />
      <EmptyState
        title="Nothing is known of that address"
        description="It was in no connection reported in the last 7 days, it is in no incident and it is not an asset. The Devices page lists the addresses that were."
        data-test="device-missing"
      />
    </template>

    <v-skeleton-loader v-else type="heading, card, card" data-test="device-loading" />
  </AppPage>
</template>

<style scoped>
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

.asset {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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
}

.row + .row {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.row__title {
  min-width: 0;
  flex: 1 1 12rem;
  overflow-wrap: anywhere;
}

.row__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  flex-basis: 100%;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}
</style>
