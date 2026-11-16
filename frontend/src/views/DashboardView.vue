<script setup lang="ts">
import {
  BellRing,
  Laptop,
  Maximize,
  Monitor,
  Radar,
  RefreshCw,
  ShieldBan,
  SlidersHorizontal,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { fetchCollectors } from '@/api/collectors'
import { LIVE_PATH } from '@/api/dashboardLayout'
import { fetchDashboard, WINDOWS, type Dashboard, type DashboardWindow } from '@/api/dashboard'
import { fetchIncidents, type IncidentPage } from '@/api/incidents'
import BarChart from '@/charts/BarChart.vue'
import { indexesWithin, useZoom } from '@/charts/zoom'
import { severityColor } from '@/charts/palette'
import AppPage from '@/components/AppPage.vue'
import BlockedCard from '@/components/BlockedCard.vue'
import DashboardCustomize from '@/components/DashboardCustomize.vue'
import EmptyState from '@/components/EmptyState.vue'
import FilteredNote from '@/components/FilteredNote.vue'
import JudgedNotice from '@/components/JudgedNotice.vue'
import LoadError from '@/components/LoadError.vue'
import NeedsYouLane from '@/components/NeedsYouLane.vue'
import NoiseCard from '@/components/NoiseCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import RecentAlerts from '@/components/RecentAlerts.vue'
import ClearedNudge from '@/components/ClearedNudge.vue'
import ReviewNudge from '@/components/ReviewNudge.vue'
import SectionCard from '@/components/SectionCard.vue'
import StatTile from '@/components/StatTile.vue'
import SinceBanner from '@/components/SinceBanner.vue'
import StatusHero from '@/components/StatusHero.vue'
import TrafficCard from '@/components/TrafficCard.vue'
import WidgetNeeds from '@/components/WidgetNeeds.vue'
import {
  alertsHint,
  alertsQuery,
  bucketLabel,
  bucketRange,
  changeOf,
  collectionOf,
  marksOf,
  needsYouLink,
  needsYouQuery,
  postureOf,
  sumBuckets,
  type Collection,
} from '@/dashboard'
import { connectWords, shownPlaces, widgetInfo, type WidgetId } from '@/dashboardLayout'
import { formatCount, formatFigure } from '@/format'
import { withinRange } from '@/logs'
import { blockedQuery, deviceQuery } from '@/blocked'
import { usePolling } from '@/polling'
import { takePrefetched } from '@/prefetch'
import { useServerEvents } from '@/serverEvents'
import { SEVERITIES, SEVERITY } from '@/severity'
import { useDashboardLayoutStore } from '@/stores/dashboardLayout'
import { useSessionStore } from '@/stores/session'
import type { Judged } from '@/verdicts'

/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30
/** How many incidents the lane under the hero shows. The rest are a click away. */
const LANE_SIZE = 3
const session = useSessionStore()
const layout = useDashboardLayoutStore()
const route = useRoute()
const router = useRouter()

const range = ref<DashboardWindow>('24h')
/** The span the owner dragged across the traffic, which narrows what the page charts. */
const zoom = useZoom()
const data = ref<Dashboard | null>(null)
const collection = ref<Collection | null>(null)
/** The integrations that have a collector, which is what a widget that needs one looks for. */
const connected = ref<ReadonlySet<string>>(new Set())
/** The incidents that need a decision. Without them the page is still the page: the lane is
 * left out until they can be read. */
const needsYou = ref<IncidentPage | null>(null)
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
    const [dashboard, collectors, incidents] = await session.call(async () => {
      // The first load of the page takes what the guard started asking for before the page's code
      // had arrived.
      const ahead = quiet ? null : takePrefetched(range.value)
      const [counted, reporting] = await Promise.all([
        ahead?.dashboard ?? fetchDashboard(range.value),
        ahead?.collectors ?? fetchCollectors(),
      ])
      // The lane lists what the banner counted, so it asks for the same thing: the floor and the
      // window are the dashboard's. With nothing that needs the owner there is nothing to list.
      const { attention, window: windowInfo } = counted
      const found =
        attention.needs_you > 0
          ? await fetchIncidents(needsYouQuery(windowInfo.start, LANE_SIZE)).catch(() => undefined)
          : null
      return [counted, reporting, found] as const
    })
    if (mine !== latest) return
    data.value = dashboard
    collection.value = collectionOf(collectors)
    connected.value = new Set(collectors.collectors.map((each) => each.integration))
    // `undefined` is a lane that could not be read, which keeps the one on screen.
    if (incidents !== undefined) needsYou.value = incidents
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

const notice = ref<{ show: (verdict: Judged) => void } | null>(null)

/** A card in the lane gave a verdict: say so, and ask again, since it can leave the lane. */
function judged(verdict: Judged) {
  notice.value?.show(verdict)
  void load(true)
}

function pick(next: DashboardWindow) {
  range.value = next
  zoom.reset()
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
  postureOf(
    view.value.shown.alerts,
    view.value.shown.attention,
    collection.value as Collection,
    view.value.shown.window.key,
  ),
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
  const { total, previous } = shown.alerts
  const { urgent, needs_you: needing } = shown.attention
  // The tone is of what needs the owner, as the banner above it is, and not of the worst alert:
  // thousands of alerts filed into incidents nobody needs to look at are no reason for red.
  let tone: 'good' | 'warning' | 'bad' = 'good'
  if (urgent > 0) tone = 'bad'
  else if (needing > 0) tone = 'warning'
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

/** Which buckets of the window the alerts are drawn for: all of them, or those of the span the
 * owner zoomed to on the traffic. */
const alertBuckets = computed(() =>
  indexesWithin(view.value.shown.window.buckets.map(Date.parse), zoom.span.value),
)
const alertCategories = computed(() =>
  alertBuckets.value.map((index) =>
    bucketLabel(view.value.shown.window.buckets[index] as string, view.value.shown.window.key),
  ),
)
/** The severities there were any of, least serious first so the worst sit on top. */
const alertSeries = computed(() =>
  SEVERITIES.flatMap((severity) => {
    const values = alertBuckets.value.map(
      (index) => view.value.shown.alerts.by_severity[severity][index] as number,
    )
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

/** A bar of the alerts opens the logs of the alerts in that stretch of time. */
function alertsOf(category: number) {
  const { buckets, end } = view.value.shown.window
  const bucket = alertBuckets.value[category] as number
  return {
    name: 'logs',
    query: { q: withinRange('kind:alert', bucketRange(buckets, bucket, end)) },
  }
}

/** A bar of the most blocked addresses opens the firewall's refusals from that address. */
function blockedFrom(index: number) {
  const source = view.value.shown.blocked.top_sources[index]
  return source
    ? { name: 'logs', query: { q: deviceQuery(source.address, view.value.shown.window.key) } }
    : null
}

/** The incidents that began in the window, flagged on the traffic. */
const marks = computed(() => marksOf(view.value.shown.marks))

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)
const lastWords = computed(() => `the last ${view.value.windowInfo.label}`)

/** What a widget says it needs connected, or null when it has it (or needs nothing). */
const needed = (id: WidgetId) => connectWords(widgetInfo(id), connected.value)

/** The widgets that are shown, in the order the account chose. */
const widgets = computed(() => shownPlaces(layout.places))

// Wall display: the page fills the screen and is for looking at from across a room. It is in the
// address (?wall), so a screen on a wall can be pointed at it and come back to it.
const wall = computed(() => 'wall' in route.query)
/** How often a wall display asks again: it is looked at, never touched. */
const WALL_REFRESH_SECONDS = 10
const customizing = ref(false)

function enterWall() {
  void router.replace({ query: { ...route.query, wall: '1' } })
}

/** Leaves full screen if the page is in it. A browser that refuses has left it already. */
async function leaveFullScreen() {
  if (!document.fullscreenElement) return
  try {
    await document.exitFullscreen()
  } catch {
    // Nothing is in full screen any more.
  }
}

async function leaveWall() {
  await leaveFullScreen()
  const query = { ...route.query }
  delete query.wall
  void router.replace({ query })
}

/** The browser only allows full screen on a click, so it is a button, not part of entering. */
async function fillScreen() {
  try {
    await document.documentElement.requestFullscreen()
  } catch {
    // The browser said no, or has no full screen (an iPhone): the page is as large as it gets.
  }
}

onMounted(() => {
  void load()
  void layout.load()
})
usePolling(() => {
  if (!wall.value) void load(true)
}, REFRESH_SECONDS * 1000)
usePolling(() => {
  if (wall.value) void load(true)
}, WALL_REFRESH_SECONDS * 1000)
// What the server says changed is looked at at once, instead of at the next turn.
const { live } = useServerEvents(LIVE_PATH, () => void load(true))
onBeforeUnmount(() => void leaveFullScreen())
</script>

<template>
  <AppPage width="wide" class="dashboard" :class="{ 'dashboard--wall': wall }">
    <PageHeader
      title="Dashboard"
      description="What is happening on your network, and whether any of it needs you."
    >
      <template #actions>
        <template v-if="wall">
          <v-btn
            variant="tonal"
            :prepend-icon="Maximize"
            data-test="wall-fullscreen"
            @click="fillScreen"
          >
            Full screen
          </v-btn>
          <v-btn variant="tonal" :prepend-icon="X" data-test="wall-exit" @click="leaveWall">
            Exit wall display
          </v-btn>
        </template>
        <template v-else>
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
          <v-btn
            variant="text"
            :prepend-icon="SlidersHorizontal"
            data-test="customize-open"
            @click="customizing = true"
          >
            Customize
          </v-btn>
          <v-btn variant="text" :prepend-icon="Monitor" data-test="wall-enter" @click="enterWall">
            Wall display
          </v-btn>
        </template>
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

      <v-alert
        v-if="wall && data.attention.urgent > 0"
        type="error"
        variant="flat"
        prominent
        role="alert"
        class="dashboard__alarm"
        data-test="wall-alarm"
      >
        <span class="text-headline-small">
          {{ formatCount(data.attention.urgent) }}
          {{ data.attention.urgent === 1 ? 'incident needs' : 'incidents need' }} you now
        </span>
        <template #append>
          <v-btn variant="outlined" :to="needsYouLink(data.attention)" data-test="wall-alarm-open">
            Look
          </v-btn>
        </template>
      </v-alert>

      <SinceBanner />

      <StatusHero :posture="posture" :action="postureAction">
        <StatTile
          flat
          label="Alerts"
          :value="alertsTile.value"
          :hint="alertsHint(data.alerts, lastWords)"
          :icon="BellRing"
          :tone="alertsTile.tone"
          :delta="alertsTile.delta"
          :trend="alertsTile.trend"
          :trend-label="alertsTile.trendLabel"
          :to="{ name: 'logs', query: { q: alertsQuery(view.shown.window.key) } }"
          :to-label="`Shows the alerts of ${lastWords}`"
          data-test="tile-alerts"
        />
        <StatTile
          flat
          label="Blocked connections"
          :value="blockedTile.value"
          :hint="`In ${lastWords}`"
          :icon="ShieldBan"
          :delta="blockedTile.delta"
          :trend="blockedTile.trend"
          :trend-label="blockedTile.trendLabel"
          :to="{ name: 'logs', query: { q: blockedQuery(view.shown.window.key) } }"
          :to-label="`Shows the blocked connections of ${lastWords}`"
          data-test="tile-blocked"
        />
        <StatTile
          flat
          label="New devices"
          :value="formatFigure(data.devices.new)"
          :hint="`${formatCount(data.devices.total)} known, first seen in ${lastWords}`"
          :icon="Laptop"
          data-test="tile-devices"
        />
        <StatTile
          flat
          label="Collection"
          :value="(collection as Collection).label"
          :hint="collectionTile.hint"
          :icon="Radar"
          :tone="collectionTile.tone"
          :to="collectionTile.to"
          data-test="tile-collection"
        />
      </StatusHero>

      <div class="dashboard__widgets" data-test="widgets">
        <div
          v-for="place in widgets"
          :key="place.id"
          class="widget"
          :class="`widget--${place.size}`"
          :data-test="`widget-${place.id}`"
        >
          <WidgetNeeds
            v-if="needed(place.id)"
            :title="widgetInfo(place.id).title"
            :words="needed(place.id) as string"
          />

          <template v-else-if="place.id === 'filtered'">
            <FilteredNote
              v-if="data.attention.incidents > 0"
              :attention="data.attention"
              :since="data.window.start"
              :last-words="lastWords"
            />
          </template>

          <div v-else-if="place.id === 'review'" class="widget__nudges">
            <ClearedNudge :counts="data.ai_review" />
            <ReviewNudge />
          </div>

          <template v-else-if="place.id === 'needs_you'">
            <NeedsYouLane
              v-if="needsYou?.items.length"
              :incidents="needsYou.items"
              :total="needsYou.total"
              :to="needsYouLink(data.attention)"
              @judged="judged"
            />
          </template>

          <TrafficCard
            v-else-if="place.id === 'traffic'"
            :times="traffic.times"
            :traffic="traffic.interfaces"
            :marks="marks"
            :span="zoom.span.value"
            :loading="loading"
            @zoom="zoom.zoom"
            @reset="zoom.reset"
          />

          <v-card v-else-if="place.id === 'alerts'" class="pa-5 pa-sm-6" data-test="alerts-card">
            <BarChart
              title="Alerts by severity"
              :caption="`Alerts in each ${view.bucketName} of ${lastWords}.`"
              category-label="Time"
              orientation="vertical"
              stacked
              whole
              :categories="alertCategories"
              :series="alertSeries"
              :to="alertsOf"
              :loading="loading"
              empty-title="No alerts"
              :empty-description="`Nothing was reported in ${lastWords}.`"
              data-test="alerts-chart"
            />
          </v-card>

          <template v-else-if="place.id === 'blocked'">
            <BlockedCard
              v-if="data.blocked.total > 0"
              :blocked="data.blocked"
              :window="data.window.key"
              :last-words="lastWords"
            />
          </template>

          <template v-else-if="place.id === 'noise'">
            <NoiseCard
              v-if="data.noise.signatures.length"
              :noise="data.noise"
              :total="data.alerts.total"
              :window="data.window.key"
              :last-words="lastWords"
              @judged="judged"
            />
          </template>

          <v-card v-else-if="place.id === 'sources'" class="pa-5 pa-sm-6" data-test="sources-card">
            <BarChart
              title="Most blocked addresses"
              :caption="`Where the firewall refused the most connections from in ${lastWords}.`"
              category-label="Address"
              whole
              :categories="data.blocked.top_sources.map(({ address }) => address)"
              :series="sourceSeries"
              :to="blockedFrom"
              :loading="loading"
              empty-title="Nothing was blocked"
              :empty-description="`The firewall refused no connections in ${lastWords}.`"
              data-test="sources-chart"
            />
          </v-card>

          <SectionCard
            v-else
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
      </div>

      <p v-if="!widgets.length" class="text-body-large text-medium-emphasis" data-test="no-widgets">
        Every widget is hidden.
        <v-btn variant="text" data-test="no-widgets-customize" @click="customizing = true">
          Customize the dashboard
        </v-btn>
      </p>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        <template v-if="live">Updated {{ updated }}. Changes appear here as they happen.</template>
        <template v-else-if="wall">
          Updated {{ updated }}. This page asks again every {{ WALL_REFRESH_SECONDS }} seconds.
        </template>
        <template v-else>
          Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it
          is open.
        </template>
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="dashboard-loading" />

    <DashboardCustomize v-model="customizing" />
    <JudgedNotice ref="notice" @undone="load(true)" />
  </AppPage>
</template>

<style scoped>
/* The page lays itself out by the room it has, not by the screen's width: the menu at the side
 * takes some of that. */
.dashboard {
  container-type: inline-size;
}

.dashboard__widgets {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-auto-flow: dense;
  gap: 1.5rem;
}

.widget {
  min-width: 0;
}

/* A widget that has nothing to show leaves no gap. */
.widget:not(:has(*)) {
  display: none;
}

.widget > * {
  height: 100%;
}

.widget__nudges {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  height: auto;
}

.widget__nudges > * {
  height: auto;
}

@container (min-width: 900px) {
  .dashboard__widgets {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .widget--full {
    grid-column: 1 / -1;
  }
}

/* A wall display is read from across a room: everything larger, and the alarm cannot be missed.
   The menu and bars are not there (App.vue). */
.dashboard--wall {
  zoom: 1.25;
}

.dashboard__alarm {
  animation: none;
}

@media (prefers-reduced-motion: no-preference) {
  .dashboard__alarm {
    animation: alarm 1.6s ease-in-out infinite;
  }
}

@keyframes alarm {
  50% {
    opacity: 0.8;
  }
}
</style>
