<script setup lang="ts">
import { BellRing, Laptop, Radar, RefreshCw, ShieldBan } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchCollectors } from '@/api/collectors'
import { fetchDashboard, WINDOWS, type Dashboard, type DashboardWindow } from '@/api/dashboard'
import BarChart from '@/charts/BarChart.vue'
import { severityColor } from '@/charts/palette'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import RecentAlerts from '@/components/RecentAlerts.vue'
import SectionCard from '@/components/SectionCard.vue'
import SecurityBanner from '@/components/SecurityBanner.vue'
import StatTile from '@/components/StatTile.vue'
import TrafficCard from '@/components/TrafficCard.vue'
import {
  bucketLabel,
  changeOf,
  collectionOf,
  postureOf,
  sumBuckets,
  type Collection,
} from '@/dashboard'
import { formatCount, formatFigure } from '@/format'
import { usePolling } from '@/polling'
import { SEVERITIES, SEVERITY } from '@/severity'
import { useSessionStore } from '@/stores/session'

/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

const session = useSessionStore()

const range = ref<DashboardWindow>('24h')
const data = ref<Dashboard | null>(null)
const collection = ref<Collection | null>(null)
const loadError = ref<string | null>(null)
/** Whether a load that someone asked for is under way: the charts dim until it is done. */
const loading = ref(false)
/** When the numbers on screen arrived. */
const updatedAt = ref<Date | null>(null)
/** Which load is the newest, so the answer to an older one (for another range) is dropped. */
let latest = 0

/** Fetches the numbers for the range. A refresh in the background (`quiet`) leaves what is on
 * screen as it is until the answer comes, and keeps it if there is none. */
async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const [dashboard, collectors] = await session.call(() =>
      Promise.all([fetchDashboard(range.value), fetchCollectors()]),
    )
    if (mine !== latest) return
    data.value = dashboard
    collection.value = collectionOf(collectors)
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

function pick(next: DashboardWindow) {
  range.value = next
  void load()
}

// The page as it is now: which range it is for, so labels fit the numbers on screen.
const view = computed(() => {
  const shown = data.value as Dashboard
  const windowInfo = WINDOWS.find(({ key }) => key === shown.window.key) as (typeof WINDOWS)[number]
  const bucketName = shown.window.key === '24h' ? 'hour' : 'six hours'
  return { shown, windowInfo, bucketName }
})

const posture = computed(() =>
  postureOf(view.value.shown.alerts, collection.value as Collection, view.value.shown.window.key),
)
const postureAction = computed(() => {
  if (posture.value.state === 'setup')
    return { label: 'Connect an integration', to: { name: 'integrations' } }
  if ((collection.value as Collection).state === 'problem')
    return { label: 'See what is wrong', to: { name: 'status' } }
  return undefined
})

const alertsTile = computed(() => {
  const { shown, windowInfo, bucketName } = view.value
  const { total, previous, highest } = shown.alerts
  let tone: 'good' | 'neutral' | 'warning' | 'bad' = 'neutral'
  if (total === 0) tone = 'good'
  else if (highest === 'high' || highest === 'critical') tone = 'bad'
  else if (highest === 'medium') tone = 'warning'
  return {
    value: formatFigure(total),
    tone,
    delta: changeOf(total, previous, windowInfo.before, true),
    trend: sumBuckets(shown.alerts.by_severity),
    trendLabel: `Alerts in each ${bucketName}`,
  }
})
const blockedTile = computed(() => {
  const { shown, windowInfo, bucketName } = view.value
  const { total, previous, per_bucket: perBucket } = shown.blocked
  return {
    value: formatFigure(total),
    delta: changeOf(total, previous, windowInfo.before, false),
    trend: perBucket,
    trendLabel: `Blocked connections in each ${bucketName}`,
  }
})
const collectionTile = computed(() => {
  const current = collection.value as Collection
  if (current.state === 'none') {
    return {
      tone: 'neutral' as const,
      hint: 'Connect an integration to start',
      to: { name: 'integrations' },
    }
  }
  const count = `${formatCount(current.total)} ${current.total === 1 ? 'collector' : 'collectors'}`
  return {
    tone: current.state === 'ok' ? ('good' as const) : ('bad' as const),
    hint: count,
    to: { name: 'status' },
  }
})

const alertCategories = computed(() =>
  view.value.shown.window.buckets.map((start) => bucketLabel(start, view.value.shown.window.key)),
)
/** The severities there were any of, least serious first so the worst sit on top. */
const alertSeries = computed(() =>
  SEVERITIES.flatMap((severity) => {
    const values = view.value.shown.alerts.by_severity[severity]
    return values.some((count) => count > 0)
      ? [
          {
            id: severity,
            label: SEVERITY[severity].label,
            values,
            color: severityColor(severity),
            icon: SEVERITY[severity].icon,
          },
        ]
      : []
  }),
)
const sourceSeries = computed(() => [
  {
    id: 'blocked',
    label: 'Blocked connections',
    values: view.value.shown.blocked.top_sources.map(({ count }) => count),
  },
])
/** The traffic up to now: the buckets still to come in the window are left off, so the lines
 * run to the right edge instead of stopping short of it. */
const traffic = computed(() => {
  const now = (updatedAt.value as Date).getTime()
  const starts = view.value.shown.window.traffic_buckets.map((start) => Date.parse(start))
  const count = starts.filter((start) => start <= now).length
  return {
    times: starts.slice(0, count),
    interfaces: view.value.shown.traffic.map((item) => ({
      ...item,
      received: item.received.slice(0, count),
      sent: item.sent.slice(0, count),
    })),
  }
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)
const lastWords = computed(() => `the last ${view.value.windowInfo.label}`)

onMounted(load)
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="dashboard">
    <PageHeader
      title="Dashboard"
      description="What is happening on your network, and whether any of it needs you."
    >
      <template #actions>
        <v-btn-toggle
          :model-value="range"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Time range"
          data-test="range"
          @update:model-value="pick"
        >
          <v-btn
            v-for="option in WINDOWS"
            :key="option.key"
            :value="option.key"
            :data-test="`range-${option.key}`"
          >
            {{ option.label }}
          </v-btn>
        </v-btn-toggle>
        <v-btn
          variant="text"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="refresh"
          @click="load()"
        >
          Refresh
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError && !data"
      :message="loadError"
      :loading="loading"
      data-test="dashboard-error"
      @retry="load()"
    />
    <template v-else-if="data">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="dashboard-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <SecurityBanner :posture="posture" :action="postureAction" />

      <div class="dashboard__tiles" data-test="tiles">
        <StatTile
          label="Alerts"
          :value="alertsTile.value"
          :hint="`In ${lastWords}`"
          :icon="BellRing"
          :tone="alertsTile.tone"
          :delta="alertsTile.delta"
          :trend="alertsTile.trend"
          :trend-label="alertsTile.trendLabel"
          data-test="tile-alerts"
        />
        <StatTile
          label="Blocked connections"
          :value="blockedTile.value"
          :hint="`In ${lastWords}`"
          :icon="ShieldBan"
          :delta="blockedTile.delta"
          :trend="blockedTile.trend"
          :trend-label="blockedTile.trendLabel"
          data-test="tile-blocked"
        />
        <StatTile
          label="New devices"
          :value="formatFigure(data.devices.new)"
          :hint="`${formatCount(data.devices.total)} known, first seen in ${lastWords}`"
          :icon="Laptop"
          data-test="tile-devices"
        />
        <StatTile
          label="Collection"
          :value="(collection as Collection).label"
          :hint="collectionTile.hint"
          :icon="Radar"
          :tone="collectionTile.tone"
          :to="collectionTile.to"
          data-test="tile-collection"
        />
      </div>

      <div class="dashboard__charts">
        <TrafficCard :times="traffic.times" :traffic="traffic.interfaces" :loading="loading" />
        <v-card class="pa-5 pa-sm-6" data-test="alerts-card">
          <BarChart
            title="Alerts by severity"
            :caption="`Alerts in each ${view.bucketName} of ${lastWords}.`"
            category-label="Time"
            orientation="vertical"
            stacked
            whole
            :categories="alertCategories"
            :series="alertSeries"
            :loading="loading"
            empty-title="No alerts"
            :empty-description="`Nothing was reported in ${lastWords}.`"
            data-test="alerts-chart"
          />
        </v-card>
      </div>

      <div class="dashboard__lists">
        <v-card class="pa-5 pa-sm-6" data-test="sources-card">
          <BarChart
            title="Most blocked addresses"
            :caption="`Where the firewall refused the most connections from in ${lastWords}.`"
            category-label="Address"
            whole
            :categories="data.blocked.top_sources.map(({ address }) => address)"
            :series="sourceSeries"
            :loading="loading"
            empty-title="Nothing was blocked"
            :empty-description="`The firewall refused no connections in ${lastWords}.`"
            data-test="sources-chart"
          />
        </v-card>
        <SectionCard
          title="Latest alerts"
          :description="`The newest of ${lastWords}.`"
          data-test="latest-alerts-card"
        >
          <RecentAlerts v-if="data.recent_alerts.length" :alerts="data.recent_alerts" />
          <EmptyState
            v-else
            title="No alerts"
            :description="`Nothing was reported in ${lastWords}.`"
          />
        </SectionCard>
      </div>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="dashboard-loading" />
  </AppPage>
</template>

<style scoped>
/* The page lays itself out by the room it has, not by the screen's width: the menu at the side
 * takes some of that. */
.dashboard {
  container-type: inline-size;
}

.dashboard__tiles,
.dashboard__charts,
.dashboard__lists {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}

/* Two numbers to a row on a phone, so the four fit without a long scroll. */
.dashboard__tiles {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

@container (min-width: 640px) {
  .dashboard__tiles {
    gap: 1.5rem;
  }
}

@container (min-width: 900px) {
  .dashboard__tiles {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .dashboard__charts {
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
  }

  .dashboard__lists {
    grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  }
}
</style>
