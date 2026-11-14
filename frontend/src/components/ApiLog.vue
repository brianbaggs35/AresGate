<script setup lang="ts">
import { CircleAlert, CircleCheck, Clock, RefreshCw } from '@lucide/vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchCalls, type Call, type CallQuery } from '@/api/integrations'
import ApiCallDialog from '@/components/ApiCallDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatTimestamp } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Every request AresGate made to an integration, newest first. Each is a button that opens all
 * that was kept of it (`ApiCallDialog`). Nothing that is a secret is recorded, and what the system
 * answered is its own text, so it is shown as plain text and nothing more.
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

/** A 429 is a limit that held the request back, which says nothing of the connection being broken. */
const limited = (call: Call) => call.status_code === 429

const said = (call: Call) =>
  limited(call) ? `${call.error}. A limit held it back, which isn't a failure.` : call.error

function mark(call: Call) {
  if (limited(call)) return { icon: Clock, color: 'info', label: 'Held by a limit' }
  if (call.error) return { icon: CircleAlert, color: 'warning', label: 'Failed' }
  return { icon: CircleCheck, color: 'success', label: 'Worked' }
}

const outcome = (call: Call) => (call.status_code === null ? 'No answer' : String(call.status_code))

/** The request the sheet shows, by its id, so that the list can be reloaded behind it. */
const selected = ref<number | null>(null)
const sheet = ref(false)
const at = computed(() => calls.value?.findIndex((one) => one.id === selected.value) ?? -1)
const shown = computed(() => (at.value >= 0 ? (calls.value?.[at.value] ?? null) : null))
const hasNewer = computed(() => at.value > 0)
const hasOlder = computed(
  () => at.value >= 0 && (at.value < (calls.value?.length ?? 0) - 1 || more.value !== null),
)

function show(call: Call) {
  selected.value = call.id
  sheet.value = true
}

/** Goes to the next older or newer request, asking for the next page when the list ends. */
async function step(direction: 'older' | 'newer') {
  const list = calls.value ?? []
  if (direction === 'newer') {
    selected.value = list[at.value - 1]?.id ?? selected.value
    return
  }
  if (at.value === list.length - 1 && more.value !== null) await load(more.value)
  selected.value = calls.value?.[at.value + 1]?.id ?? selected.value
}

// A reload that no longer has the request leaves nothing to show.
watch(shown, (now) => {
  if (!now) sheet.value = false
})
watch(filters, () => load())
watch(
  () => props.refresh,
  () => load(),
)
onMounted(() => load())
</script>

<template>
  <SectionCard
    title="API log"
    description="Every request AresGate makes to this system, newest first. Open one to see all that was kept of it. Secrets are never recorded, and what the system answered is shown as plain text, since it can't be trusted. Old requests are deleted automatically."
    data-test="api-log"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="log-refresh"
        @click="load()"
      >
        Refresh
      </v-btn>
    </template>

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

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="log-retry"
      class="mt-4"
      data-test="log-error"
      @retry="load()"
    />
    <template v-if="calls?.length">
      <ul class="api-log__calls" data-test="log-calls">
        <li v-for="call in calls" :key="call.id">
          <button
            type="button"
            class="api-call"
            aria-haspopup="dialog"
            data-test="log-call"
            @click="show(call)"
          >
            <v-icon
              :icon="mark(call).icon"
              :color="mark(call).color"
              :aria-label="mark(call).label"
              role="img"
              :aria-hidden="false"
            />
            <span class="api-call__text">
              <span class="api-call__line text-body-large">
                <span class="api-call__method" data-test="call-method">{{ call.method }}</span>
                <code class="api-call__path" data-test="call-path">{{ call.path }}</code>
              </span>
              <span
                class="api-call__line text-body-medium text-medium-emphasis"
                data-test="call-detail"
              >
                <time :datetime="call.occurred_at">{{ formatTimestamp(call.occurred_at) }}</time>
                · {{ outcome(call) }} · {{ call.duration_ms }} ms<template
                  v-if="connections.length > 1"
                >
                  · {{ labels.get(call.connection) ?? call.connection }}</template
                >
              </span>
              <span
                v-if="call.error"
                class="api-call__line text-body-medium"
                :class="limited(call) ? 'text-medium-emphasis' : 'text-error'"
                data-test="call-error"
              >
                {{ said(call) }}
              </span>
            </span>
          </button>
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
    <EmptyState
      v-else-if="calls"
      :title="
        filtered
          ? 'No requests match these filters.'
          : `AresGate hasn't made a request to this system yet.`
      "
      data-test="log-empty"
    >
      <v-btn v-if="filtered" variant="tonal" data-test="log-clear" @click="clearFilters">
        Clear the filters
      </v-btn>
    </EmptyState>
    <ApiCallDialog
      v-model="sheet"
      :integration="integration"
      :call="shown"
      :connection="
        connections.length > 1 && shown ? (labels.get(shown.connection) ?? shown.connection) : null
      "
      :has-older="hasOlder"
      :has-newer="hasNewer"
      @step="step"
    />
  </SectionCard>
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
  width: 100%;
  padding: 0.75rem 0.5rem;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.api-call:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.api-call:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.api-log__calls li + li {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.api-call__line {
  display: block;
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
