<script setup lang="ts">
import { Ban, Check, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import {
  FLOW_DIRECTIONS,
  FLOW_HOURS,
  fetchFlow,
  type Flow,
  type FlowDirection,
  type FlowHours,
} from '@/api/flow'
import AppPage from '@/components/AppPage.vue'
import FlowDetail from '@/components/FlowDetail.vue'
import FlowSankey from '@/components/FlowSankey.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import BarChart from '@/charts/BarChart.vue'
import { formatCount } from '@/format'
import {
  DIRECTION_LABELS,
  DIRECTION_MEANINGS,
  WINDOW_LABELS,
  refusedShare,
  timelineBars,
} from '@/flow'
import { withinRange } from '@/logs'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/**
 * Network Flow: where the traffic goes. The connections the firewall wrote down in the last hour,
 * six hours, day or week are drawn as paths from who connected, through the service, to what they
 * reached (`FlowSankey`), with how many came in each stretch of the window under it. Picking a
 * block says what it is (`FlowDetail`) and leads to the logs that make it up; picking a bar of the
 * timeline leads to the logs of that time. The window and the direction are in the address of the
 * page, so a link brings it back as it was.
 */
const REFRESH_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const hours = computed<FlowHours>(
  () => FLOW_HOURS.find((choice) => choice.toString() === route.query.hours) ?? 24,
)
const direction = computed<FlowDirection>(
  () => FLOW_DIRECTIONS.find((choice) => choice === route.query.direction) ?? 'all',
)

function show(next: { hours?: FlowHours; direction?: FlowDirection }) {
  const merged = { hours: hours.value, direction: direction.value, ...next }
  const query: Record<string, string> = {}
  if (merged.hours !== 24) query.hours = merged.hours.toString()
  if (merged.direction !== 'all') query.direction = merged.direction
  void router.replace({ query })
}

const data = ref<Flow | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const updatedAt = ref<Date | null>(null)
const selected = ref<string | null>(null)
/** Which load is the newest, so the answer to an older one (for another window) is dropped. */
let latest = 0

async function load(quiet = false) {
  const mine = ++latest
  const [asked, way] = [hours.value, direction.value]
  if (!quiet) loading.value = true
  try {
    const flow = await session.call(() => fetchFlow(asked, way))
    if (mine !== latest) return
    data.value = flow
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

watch([hours, direction], () => {
  selected.value = null
  void load()
})
onMounted(() => void load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)

const picked = computed(
  () => (data.value as Flow).nodes.find((node) => node.id === selected.value) ?? null,
)
const bars = computed(() =>
  timelineBars((data.value as Flow).timeline, (data.value as Flow).stride_seconds),
)
const series = computed(() => [
  {
    id: 'allowed',
    label: 'Let through',
    values: bars.value.allowed,
    color: 'var(--chart-1)',
    icon: Check,
  },
  {
    id: 'blocked',
    label: 'Refused',
    values: bars.value.blocked,
    color: 'var(--chart-severity-high)',
    icon: Ban,
  },
])

/** A bar of the timeline was picked: the logs of that stretch of time. */
function pickBar(index: number) {
  const range = bars.value.ranges[index]
  if (!range) return
  void router.push({ name: 'logs', query: { q: withinRange('kind:firewall', range) } })
}

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)
const caption = computed(() => {
  const { capped, direction: way } = data.value as Flow
  const limit = capped ? ' This is the busiest of what was seen: there was more than is read.' : ''
  return `${DIRECTION_MEANINGS[way]}.${limit}`
})
</script>

<template>
  <AppPage class="flow-page">
    <PageHeader
      title="Network Flow"
      description="Where the traffic on your network goes, as your firewall wrote it down: who connected, which service they used and what they reached."
    >
      <template #actions>
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
      data-test="flow-error"
      @retry="load()"
    />
    <template v-else-if="data">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="flow-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <div class="flow-page__controls">
        <v-btn-toggle
          :model-value="hours"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="How far back"
          data-test="window"
          @update:model-value="(value: FlowHours) => show({ hours: value })"
        >
          <v-btn
            v-for="choice in FLOW_HOURS"
            :key="choice"
            :value="choice"
            :aria-pressed="hours === choice"
            :data-test="`window-${choice}`"
          >
            {{ WINDOW_LABELS[choice] }}
          </v-btn>
        </v-btn-toggle>
        <v-btn-toggle
          :model-value="direction"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Which connections"
          data-test="direction"
          @update:model-value="(value: FlowDirection) => show({ direction: value })"
        >
          <v-btn
            v-for="choice in FLOW_DIRECTIONS"
            :key="choice"
            :value="choice"
            :title="DIRECTION_MEANINGS[choice]"
            :aria-pressed="direction === choice"
            :data-test="`direction-${choice}`"
          >
            {{ DIRECTION_LABELS[choice] }}
          </v-btn>
        </v-btn-toggle>
      </div>

      <dl class="flow-page__stats" data-test="flow-stats">
        <div>
          <dt class="text-label-large text-medium-emphasis">Connections</dt>
          <dd class="text-headline-small tabular-nums" data-test="stat-events">
            {{ formatCount(data.events) }}
          </dd>
        </div>
        <div>
          <dt class="text-label-large text-medium-emphasis">Refused</dt>
          <dd class="text-headline-small tabular-nums" data-test="stat-blocked">
            {{ formatCount(data.blocked) }}
            <span class="text-body-medium text-medium-emphasis"
              >({{ refusedShare(data.events, data.blocked) }}%)</span
            >
          </dd>
        </div>
        <p
          class="text-body-medium text-medium-emphasis flow-page__caption"
          data-test="flow-caption"
        >
          {{ caption }}
        </p>
      </dl>

      <div class="flow-page__main">
        <v-card class="pa-4 pa-sm-5 flow-page__chart" data-test="flow-card">
          <FlowSankey
            :flow="data"
            :selected="selected"
            :loading="loading"
            @select="selected = $event"
          />
        </v-card>
        <v-card v-if="picked" class="pa-4 pa-sm-5 flow-page__detail">
          <FlowDetail :flow="data" :node="picked" :hours="hours" @close="selected = null" />
        </v-card>
      </div>

      <v-card class="pa-4 pa-sm-5">
        <BarChart
          title="Connections over time"
          caption="Let through and refused in each stretch of the window. Pick a bar to read its logs."
          category-label="Time"
          orientation="vertical"
          stacked
          whole
          selectable
          :height="180"
          :categories="bars.categories"
          :series="series"
          :loading="loading"
          empty-title="No connections"
          empty-description="The firewall wrote nothing down in this window."
          data-test="flow-timeline"
          @select="pickBar"
        />
      </v-card>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open. A connection is one the firewall wrote down, not a count of bytes.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="flow-loading" />
  </AppPage>
</template>

<style scoped>
.flow-page__controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  overflow-x: auto;
}

.flow-page__stats {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.5rem 2.5rem;
  margin: 0;
}

.flow-page__stats dd {
  margin: 0;
}

.flow-page__caption {
  flex-basis: 100%;
  margin: 0;
}

.flow-page__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem;
}

@media (min-width: 1100px) {
  .flow-page__main:has(.flow-page__detail) {
    grid-template-columns: minmax(0, 1fr) 22rem;
    align-items: start;
  }
}
</style>
