<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { fetchDeliveries, type Deliveries, type Delivery, type DeliveryQuery } from '@/api/alerts'
import { errorMessage } from '@/api/client'
import { DELIVERY_REASONS, DELIVERY_STATES, deliveryTitle, deliveryTotals } from '@/alerts'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { formatAgo } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Every message AresGate sent to a destination, newest first: what was sent, what is waiting
 * (for quiet hours to end, or to be tried again), what the limit an hour held back and what
 * was left out because the owner dealt with it first, each with the reason in words. It only
 * shows what AresGate wrote itself; what a message said is not kept.
 */
const props = defineProps<{
  /** The destinations, to tell the messages apart when there are several. */
  destinations: readonly { id: number; name: string }[]
}>()

const STATES = [
  { title: 'Any state', value: 'all' },
  ...Object.entries(DELIVERY_STATES).map(([value, { label }]) => ({ title: label, value })),
]

const session = useSessionStore()

const filters = reactive({ destination: 'all', state: 'all' })
const answer = ref<Deliveries | null>(null)
const items = ref<Delivery[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref<string | null>(null)
/** Only the newest request's answer counts, so a slow one can't replace a later one. */
let latest = 0

const filtered = computed(() => filters.destination !== 'all' || filters.state !== 'all')
const destinationItems = computed(() => [
  { title: 'Any destination', value: 'all' },
  ...props.destinations.map(({ id, name }) => ({ title: name, value: id.toString() })),
])
const more = computed(() => answer.value?.next_before ?? null)

function query(before?: number): DeliveryQuery {
  const asked: DeliveryQuery = {}
  if (filters.destination !== 'all') asked.destination_id = Number(filters.destination)
  if (filters.state !== 'all') asked.state = filters.state as DeliveryQuery['state']
  if (before !== undefined) asked.before = before
  return asked
}

/** Loads the newest messages, or, given where the ones shown end, the page after them. */
async function load(before?: number) {
  const mine = ++latest
  const older = before !== undefined
  error.value = null
  if (older) loadingMore.value = true
  else loading.value = true
  try {
    const page = await session.call(() => fetchDeliveries(query(before)))
    if (mine !== latest) return
    answer.value = page
    items.value = older ? [...items.value, ...page.items] : page.items
  } catch (loadError) {
    if (mine === latest) {
      error.value = errorMessage(loadError)
      // The list on screen is no longer what the filters ask for.
      if (!older) answer.value = null
    }
  } finally {
    if (mine === latest) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function clearFilters() {
  Object.assign(filters, { destination: 'all', state: 'all' })
}

/** When a message was sent or, if it was not, when it was made, or is due. */
function when(delivery: Delivery): string {
  if (delivery.sent_at) return `sent ${formatAgo(delivery.sent_at)}`
  if (DELIVERY_STATES[delivery.state].waiting) return `due ${formatAgo(delivery.due_at)}`
  return `made ${formatAgo(delivery.created_at)}`
}

watch(filters, () => load())
onMounted(() => load())
</script>

<template>
  <SectionCard
    title="Delivery log"
    description="Every message AresGate sent to a destination, and what became of the ones it did not: waiting for quiet hours to end, held back by the limit an hour, told in a summary, or left out because you dealt with the incident first. Old entries are deleted automatically."
    data-test="delivery-log"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="delivery-refresh"
        @click="load()"
      >
        Refresh
      </v-btn>
    </template>

    <p v-if="answer" class="text-body-large mb-3" aria-live="polite" data-test="delivery-totals">
      {{ deliveryTotals(answer.counts) }}
    </p>

    <div class="delivery-log__filters">
      <v-select
        v-if="destinations.length > 1"
        v-model="filters.destination"
        :items="destinationItems"
        label="Destination"
        density="compact"
        hide-details
        data-test="delivery-filter-destination"
      />
      <v-select
        v-model="filters.state"
        :items="STATES"
        label="State"
        density="compact"
        hide-details
        data-test="delivery-filter-state"
      />
    </div>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="delivery-retry"
      class="mt-4"
      data-test="delivery-error"
      @retry="load()"
    />
    <template v-if="items.length">
      <ul class="delivery-log__list" data-test="delivery-list">
        <li v-for="item in items" :key="item.id" class="delivery" data-test="delivery">
          <div class="delivery__head">
            <v-chip
              :color="DELIVERY_STATES[item.state].color"
              variant="tonal"
              size="small"
              data-test="delivery-state"
            >
              {{ DELIVERY_STATES[item.state].label }}
            </v-chip>
            <SeverityChip v-if="item.kind === 'incident'" :severity="item.severity" />
          </div>
          <router-link
            v-if="item.incident_id !== null"
            :to="`/incidents/${item.incident_id.toString()}`"
            class="delivery__title text-body-large"
            data-test="delivery-title"
          >
            {{ deliveryTitle(item) }}
          </router-link>
          <div v-else class="delivery__title text-body-large" data-test="delivery-title">
            {{ deliveryTitle(item) }}
          </div>
          <div class="text-body-medium text-medium-emphasis" data-test="delivery-detail">
            {{ item.destination }} · {{ DELIVERY_REASONS[item.reason] }} · {{ when(item)
            }}<template v-if="item.attempts > 1"> · {{ item.attempts }} tries</template>
          </div>
          <div v-if="item.note" class="text-body-medium" data-test="delivery-note">
            {{ item.note }}
          </div>
        </li>
      </ul>
      <div v-if="more !== null" class="mt-2">
        <v-btn
          variant="tonal"
          :loading="loadingMore"
          data-test="delivery-older"
          @click="load(more)"
        >
          Show older messages
        </v-btn>
      </div>
    </template>
    <v-skeleton-loader
      v-else-if="!answer && !error"
      class="mt-2"
      type="list-item-two-line, list-item-two-line, list-item-two-line"
    />
    <EmptyState
      v-else-if="answer"
      :title="
        filtered
          ? 'No messages match these filters.'
          : 'Nothing has been sent yet. When a destination is told of an incident it appears here.'
      "
      data-test="delivery-empty"
    >
      <v-btn v-if="filtered" variant="tonal" data-test="delivery-clear" @click="clearFilters">
        Clear the filters
      </v-btn>
    </EmptyState>
  </SectionCard>
</template>

<style scoped>
.delivery-log__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.75rem;
}

.delivery-log__list {
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.delivery {
  display: grid;
  gap: 0.25rem;
  padding: 0.75rem 0;
  overflow-wrap: anywhere;
}

.delivery + .delivery {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.delivery__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
