<script setup lang="ts">
import { CircleAlert, CircleCheck, RefreshCw } from '@lucide/vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchCalls, type Call, type CallQuery } from '@/api/integrations'
import { formatTimestamp } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Every request AresGate made to an integration, newest first. Only what is safe to keep is
 * recorded (no secret, no query string), and what the system answered is its own text, so it is
 * shown as plain text and nothing more.
 */
const props = defineProps<{
  integration: string
  /** Its connections, to tell the calls apart when there are several. */
  connections: readonly { key: string; label: string }[]
  /** Changes when something happened that made calls, such as a test: the log reloads. */
  refresh: number
}>()

const PAGE = 25
const HOUR = 3_600_000

const RESULTS = [
  { title: 'Any result', value: 'all' },
  { title: 'Failed', value: 'failed' },
  { title: 'Worked', value: 'ok' },
]
const METHODS = [
  { title: 'Any method', value: 'all' },
  { title: 'GET', value: 'GET' },
  { title: 'POST', value: 'POST' },
]
const PERIODS = [
  { title: 'All time', value: 'all' },
  { title: 'Last hour', value: 'hour' },
  { title: 'Last 24 hours', value: 'day' },
  { title: 'Last 7 days', value: 'week' },
]
/** How far back each period goes, in hours. */
const HOURS: Readonly<Record<string, number>> = { hour: 1, day: 24, week: 168 }

const session = useSessionStore()

const filters = reactive({ connection: 'all', result: 'all', method: 'all', period: 'all' })
const calls = ref<Call[] | null>(null)
/** Where the next page of older calls starts, if there is one. */
const more = ref<number | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref<string | null>(null)
/** Only the newest request's answer counts, so a slow one can't replace a later one. */
let latest = 0

const filtered = computed(
  () =>
    filters.connection !== 'all' ||
    filters.result !== 'all' ||
    filters.method !== 'all' ||
    filters.period !== 'all',
)
const connectionItems = computed(() => [
  { title: 'Any connection', value: 'all' },
  ...props.connections.map(({ key, label }) => ({ title: label, value: key })),
])
const labels = computed(() => new Map(props.connections.map(({ key, label }) => [key, label])))

function query(before?: number): CallQuery {
  const asked: CallQuery = { limit: PAGE }
  if (filters.connection !== 'all') asked.connection = filters.connection
  if (filters.method !== 'all') asked.method = filters.method
  if (filters.result !== 'all') asked.failed = filters.result === 'failed'
  const hours = HOURS[filters.period]
  if (hours) asked.since = new Date(Date.now() - hours * HOUR).toISOString()
  if (before !== undefined) asked.before = before
  return asked
}

/** Loads the newest calls, or, given where the ones shown end, the page after them. */
async function load(before?: number) {
  const mine = ++latest
  const older = before !== undefined
  error.value = null
  if (older) loadingMore.value = true
  else loading.value = true
  try {
    const page = await session.call(() => fetchCalls(props.integration, query(before)))
    if (mine !== latest) return
    const shown = calls.value ?? []
    calls.value = older ? [...shown, ...page.calls] : page.calls
    more.value = page.next_before
  } catch (loadError) {
    if (mine === latest) {
      error.value = errorMessage(loadError)
      // The list on screen is no longer what the filters ask for. (Older requests that couldn't
      // be read leave the newer ones where they are.)
      if (!older) calls.value = null
    }
  } finally {
    if (mine === latest) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function clearFilters() {
  Object.assign(filters, { connection: 'all', result: 'all', method: 'all', period: 'all' })
}

const outcome = (call: Call) => (call.status_code === null ? 'No answer' : String(call.status_code))

watch(filters, () => load())
watch(
  () => props.refresh,
  () => load(),
)
onMounted(() => load())
</script>

<template>
  <v-card class="pa-6" data-test="api-log">
    <div class="d-flex align-center justify-space-between ga-3 mb-1">
      <h2 class="text-title-large">API log</h2>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="log-refresh"
        @click="load()"
      >
        Refresh
      </v-btn>
    </div>
    <p class="text-body-medium text-medium-emphasis mb-4">
      Every request AresGate makes to this system, newest first. Secrets and query strings are never
      recorded, and what the system answered is shown as plain text, since it can't be trusted. Old
      requests are deleted automatically.
    </p>

    <div class="api-log__filters">
      <v-select
        v-if="connections.length > 1"
        v-model="filters.connection"
        :items="connectionItems"
        label="Connection"
        density="compact"
        hide-details
        data-test="filter-connection"
      />
      <v-select
        v-model="filters.result"
        :items="RESULTS"
        label="Result"
        density="compact"
        hide-details
        data-test="filter-result"
      />
      <v-select
        v-model="filters.method"
        :items="METHODS"
        label="Method"
        density="compact"
        hide-details
        data-test="filter-method"
      />
      <v-select
        v-model="filters.period"
        :items="PERIODS"
        label="When"
        density="compact"
        hide-details
        data-test="filter-period"
      />
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mt-4" data-test="log-error">
      {{ error }}
      <template #append>
        <v-btn variant="text" data-test="log-retry" @click="load()">Try again</v-btn>
      </template>
    </v-alert>
    <template v-if="calls?.length">
      <ul class="api-log__calls" data-test="log-calls">
        <li v-for="call in calls" :key="call.id" class="api-call" data-test="log-call">
          <v-icon
            :icon="call.error ? CircleAlert : CircleCheck"
            :color="call.error ? 'warning' : 'success'"
            :aria-label="call.error ? 'Failed' : 'Worked'"
            role="img"
            :aria-hidden="false"
          />
          <div class="api-call__text">
            <div class="text-body-large">
              <span class="api-call__method" data-test="call-method">{{ call.method }}</span>
              <code class="api-call__path" data-test="call-path">{{ call.path }}</code>
            </div>
            <div class="text-body-medium text-medium-emphasis" data-test="call-detail">
              <time :datetime="call.occurred_at">{{ formatTimestamp(call.occurred_at) }}</time>
              · {{ outcome(call) }} · {{ call.duration_ms }} ms<template
                v-if="connections.length > 1"
              >
                · {{ labels.get(call.connection) ?? call.connection }}</template
              >
            </div>
            <div v-if="call.error" class="text-body-medium text-error" data-test="call-error">
              {{ call.error }}
            </div>
          </div>
        </li>
      </ul>
      <div v-if="more !== null" class="mt-2">
        <v-btn variant="tonal" :loading="loadingMore" data-test="log-older" @click="load(more)">
          Show older requests
        </v-btn>
      </div>
    </template>
    <v-skeleton-loader
      v-else-if="!calls && !error"
      class="mt-2"
      type="list-item-two-line, list-item-two-line, list-item-two-line"
    />
    <div v-else-if="calls" class="py-4" data-test="log-empty">
      <p v-if="filtered" class="text-body-large mb-2">No requests match these filters.</p>
      <p v-else class="text-body-large">AresGate hasn't made a request to this system yet.</p>
      <v-btn v-if="filtered" variant="tonal" data-test="log-clear" @click="clearFilters">
        Clear the filters
      </v-btn>
    </div>
  </v-card>
</template>

<style scoped>
.api-log__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.75rem;
}

.api-log__calls {
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.api-call {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.api-call + .api-call {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.api-call__text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.api-call__method {
  margin-right: 0.5rem;
  font-weight: 600;
}

.api-call__path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em;
}
</style>
