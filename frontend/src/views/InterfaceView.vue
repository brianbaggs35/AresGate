<script setup lang="ts">
import { Pencil } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { Feed, OverviewWindow, Placement } from '@/api/interfaces'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import FeedRow from '@/components/FeedRow.vue'
import InterfaceEditor from '@/components/InterfaceEditor.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatTile from '@/components/StatTile.vue'
import UndoNotice from '@/components/UndoNotice.vue'
import { formatBitrate, formatCount } from '@/format'
import { useInterfaceBoard, type Done } from '@/interface-board'
import { latestSpeed, roleInfo, totalSpeed } from '@/interfaces'

/**
 * One part of the network: what it is for, how its traffic has gone, how many alerts came in on it
 * and how many devices live on it, and the feeds that are placed on it, each with a control to
 * move it somewhere else.
 */
const route = useRoute()
const router = useRouter()
const board = useInterfaceBoard()
const { listing, overview, loading, error, problem, busy } = board

const WINDOWS: readonly { key: OverviewWindow; label: string }[] = [
  { key: '24h', label: '24 hours' },
  { key: '7d', label: '7 days' },
]

const notice = ref<{ show: (done: Done) => void } | null>(null)
const editing = ref(false)
const range = ref<OverviewWindow>('24h')

const id = computed(() => Number(route.params.id))
const item = computed(() => listing.value?.interfaces.find((each) => each.id === id.value))
const stats = computed(() => overview.value?.stats.find((each) => each.interface_id === id.value))
const role = computed(() => (item.value ? roleInfo(item.value.role) : null))
const times = computed(() => (overview.value?.times ?? []).map((time) => Date.parse(time)))
const series = computed(() =>
  stats.value?.speed
    ? [
        { id: 'received', label: 'Received', values: stats.value.speed.received },
        { id: 'sent', label: 'Sent', values: stats.value.speed.sent },
      ]
    : [],
)
const received = computed(() =>
  stats.value?.speed ? latestSpeed(stats.value.speed.received) : null,
)
const sent = computed(() => (stats.value?.speed ? latestSpeed(stats.value.speed.sent) : null))
const trend = computed(() => (stats.value?.speed ? totalSpeed(stats.value.speed) : []))
const days = computed(() => (range.value === '24h' ? 'last 24 hours' : 'last 7 days'))

function show(done: Done | null) {
  if (done) notice.value?.show(done)
}

function move(feed: Feed, placement: Placement) {
  return board.move(feed, placement).then(show)
}

function pick(next: OverviewWindow) {
  range.value = next
  return board.load(next)
}

function removed() {
  return router.push({ name: 'interfaces' })
}

async function saved(text: string) {
  await board.load()
  show({ text, undo: null })
}

async function undo(done: Done) {
  show(await board.undo(done))
}

onMounted(() => board.load(range.value))
</script>

<template>
  <AppPage width="wide">
    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="interface-retry"
      data-test="interface-error"
      @retry="board.load(range)"
    />

    <template v-else-if="item && role">
      <PageHeader
        :title="item.name"
        :description="item.notes || role.description"
        :back="{ to: { name: 'interfaces' }, label: 'Interfaces' }"
      >
        <template #badge>
          <v-chip :prepend-icon="role.icon" size="small" variant="tonal" data-test="interface-role">
            {{ role.label }}
          </v-chip>
        </template>
        <template #actions>
          <v-btn
            variant="tonal"
            :prepend-icon="Pencil"
            data-test="interface-edit"
            @click="editing = true"
          >
            Edit
          </v-btn>
        </template>
      </PageHeader>

      <v-alert
        v-if="problem"
        type="error"
        variant="tonal"
        density="compact"
        data-test="interface-problem"
      >
        {{ problem }}
      </v-alert>

      <v-btn-toggle
        :model-value="range"
        mandatory
        density="comfortable"
        variant="outlined"
        divided
        aria-label="How far back to look"
        class="windows"
        data-test="interface-window"
        @update:model-value="pick"
      >
        <v-btn v-for="each in WINDOWS" :key="each.key" :value="each.key">{{ each.label }}</v-btn>
      </v-btn-toggle>

      <div class="tiles">
        <StatTile
          label="Received now"
          :value="received === null ? '–' : formatBitrate(received)"
          :hint="stats?.speed ? `From ${stats.speed.source_name}` : 'Nothing measured yet'"
          :trend="trend"
          trend-label="Traffic through this interface"
          data-test="interface-tile-received"
        />
        <StatTile
          label="Sent now"
          :value="sent === null ? '–' : formatBitrate(sent)"
          :hint="stats?.speed ? `From ${stats.speed.source_name}` : 'Nothing measured yet'"
          data-test="interface-tile-sent"
        />
        <StatTile
          label="Alerts"
          :value="formatCount(stats?.alerts ?? 0)"
          :hint="`In the ${days}`"
          data-test="interface-tile-alerts"
        />
        <StatTile
          label="Devices"
          :value="stats?.devices === null || !stats ? '–' : formatCount(stats.devices)"
          :hint="stats?.devices === null ? 'Add its networks to count them' : 'On its networks'"
          data-test="interface-tile-devices"
        />
      </div>

      <v-card class="pa-5 pa-sm-6">
        <TimeSeriesChart
          title="Traffic"
          :caption="
            stats?.speed
              ? `Speed through ${item.name}, from ${stats.speed.source_name}'s byte counters.`
              : undefined
          "
          :times="times"
          :series="series"
          :format="formatBitrate"
          :loading="loading"
          empty-title="No traffic measured yet"
          empty-description="Place the firewall's or ntopng's interface on this one, and the bytes through it are charted here."
          data-test="interface-chart"
        />
      </v-card>

      <section v-if="item.networks.length" class="section" aria-labelledby="networks-title">
        <h2 id="networks-title" class="text-title-large">Networks</h2>
        <ul class="chips">
          <li v-for="network in item.networks" :key="network">
            <v-chip variant="outlined" data-test="interface-network">{{ network }}</v-chip>
          </li>
        </ul>
      </section>

      <section class="section" aria-labelledby="sources-title" data-test="interface-sources">
        <h2 id="sources-title" class="text-title-large">Data sources</h2>
        <p
          v-if="item.feeds.length === 0"
          class="text-body-large text-medium-emphasis"
          data-test="interface-no-sources"
        >
          Nothing is placed on this interface yet. Place a feed on it from the Interfaces page.
        </p>
        <v-card v-else class="rows">
          <FeedRow
            v-for="feed in item.feeds"
            :key="feed.id"
            :feed="feed"
            :interfaces="listing?.interfaces ?? []"
            :disabled="busy"
            :can-create="false"
            @move="move(feed, $event)"
          />
        </v-card>
      </section>

      <InterfaceEditor v-model="editing" :interface="item" @saved="saved" @removed="removed" />
    </template>

    <template v-else-if="listing">
      <PageHeader title="Interfaces" :back="{ to: { name: 'interfaces' }, label: 'Interfaces' }" />
      <EmptyState
        title="That interface isn't there"
        description="It may have been removed. The Interfaces page lists the ones you have."
        data-test="interface-missing"
      />
    </template>

    <v-skeleton-loader v-else type="heading, card, card" data-test="interface-loading" />

    <UndoNotice ref="notice" @undo="undo" />
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

.rows > :deep(.feed + .feed) {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
