<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchCollectors,
  type Collector,
  type CollectorsReport,
  type WorkerState,
} from '@/api/collectors'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatAgo, formatDue, formatElapsed } from '@/format'
import { COLLECTOR_STATE } from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * How AresGate's regular reading from an integration is going: each job the worker runs on it,
 * when it last ran, when it runs next and, if it failed, why. When the worker itself isn't
 * running that comes first, because nothing below it is being kept up to date.
 */
const props = defineProps<{
  integration: string
  /** Its connections, to tell jobs apart when there are several. */
  connections: readonly { key: string; label: string }[]
  /** Changes when something happened that makes the jobs run, such as a test: it reloads. */
  refresh: number
}>()

/** What to say about a worker that isn't running; one that is has nothing to say. */
const WORKER_NOTES: Readonly<
  Record<WorkerState, { type: 'warning' | 'info'; text: string } | null>
> = {
  running: null,
  stopped: {
    type: 'warning',
    text: "The collector worker has stopped reporting in, so nothing is being collected. Restart AresGate, and look at Status if it doesn't come back.",
  },
  unknown: {
    type: 'info',
    text: "The collector worker hasn't reported in yet. It starts a few seconds after AresGate does.",
  },
  off: {
    type: 'info',
    text: 'Collecting is turned off (ARESGATE_COLLECTORS_ENABLED is false). Nothing is read from this system until it is turned on.',
  },
}

const session = useSessionStore()

const report = ref<CollectorsReport | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const several = computed(() => props.connections.length > 1)
const labels = computed(() => new Map(props.connections.map(({ key, label }) => [key, label])))
const note = computed(() => WORKER_NOTES[(report.value as CollectorsReport).worker.state])

/** A job's name, with the connection it reads from when the integration has several. */
function heading(collector: Collector): string {
  const connection = labels.value.get(collector.connection) ?? collector.connection
  return several.value ? `${collector.title} · ${connection}` : collector.title
}

/** When it last ran and how that went, and when it runs next. */
function timing(collector: Collector): string {
  if (!collector.last_finished_at) return "Hasn't run yet. The first run is due shortly."
  const ran = `Last ran ${formatAgo(collector.last_finished_at)}`
  const took =
    collector.last_duration_ms === null ? '' : `, took ${formatElapsed(collector.last_duration_ms)}`
  const parts = [ran + took]
  if (collector.last_items !== null) {
    parts.push(`collected ${collector.last_items.toString()}`)
  }
  if (collector.next_run_at) parts.push(`next run ${formatDue(collector.next_run_at)}`)
  return parts.join(' · ')
}

async function load() {
  loading.value = true
  error.value = null
  try {
    report.value = await session.call(() => fetchCollectors(props.integration))
  } catch (loadError) {
    // What is on screen is no longer how things are, so it goes rather than mislead.
    report.value = null
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.refresh,
  () => load(),
)
onMounted(load)
</script>

<template>
  <SectionCard
    title="Collection"
    description="AresGate reads from this system on a schedule. This is how each job is doing."
    data-test="collection"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="collection-refresh"
        @click="load"
      >
        Refresh
      </v-btn>
    </template>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="collection-retry"
      data-test="collection-error"
      @retry="load"
    />
    <v-skeleton-loader
      v-else-if="!report"
      type="list-item-two-line"
      data-test="collection-loading"
    />
    <template v-else>
      <v-alert
        v-if="note"
        :type="note.type"
        variant="tonal"
        density="compact"
        class="mb-3"
        data-test="collection-worker"
      >
        {{ note.text }}
      </v-alert>
      <p
        v-if="!report.collectors.length"
        class="text-body-medium text-medium-emphasis"
        data-test="collection-empty"
      >
        Nothing is being collected from this system yet. Jobs start a few seconds after it is
        connected.
      </p>
      <ul v-else class="collection__list">
        <li
          v-for="collector in report.collectors"
          :key="`${collector.collector}/${collector.connection}`"
          class="collection__job"
          data-test="collector"
        >
          <div class="text-body-large">
            <span data-test="collector-title">{{ heading(collector) }}</span>
            <v-chip
              :color="COLLECTOR_STATE[collector.state].color"
              :prepend-icon="COLLECTOR_STATE[collector.state].icon"
              size="small"
              variant="tonal"
              class="ml-2"
              data-test="collector-state"
            >
              {{ COLLECTOR_STATE[collector.state].label }}
            </v-chip>
          </div>
          <p class="text-body-medium text-medium-emphasis" data-test="collector-summary">
            {{ collector.summary }}
          </p>
          <p class="text-body-medium" data-test="collector-timing">{{ timing(collector) }}</p>
          <p
            v-if="collector.last_error"
            class="text-body-medium text-error"
            data-test="collector-error"
          >
            {{ collector.last_error }}
          </p>
        </li>
      </ul>
    </template>
  </SectionCard>
</template>

<style scoped>
.collection__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.collection__job {
  padding: 0.75rem 0;
  overflow-wrap: anywhere;
}

.collection__job + .collection__job {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.collection__job p {
  margin: 0.25rem 0 0;
}
</style>
