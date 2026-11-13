<script setup lang="ts">
import { Radar, RefreshCw } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { DEVICE_DIRECTIONS, DEVICE_SCOPES, fetchDevices, type DevicePage } from '@/api/devices'
import type { Device } from '@/api/devices'
import { errorMessage } from '@/api/client'
import AppPage from '@/components/AppPage.vue'
import AssetSearch from '@/components/AssetSearch.vue'
import DeviceCard from '@/components/DeviceCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  DIRECTION,
  NO_FILTERS,
  SCOPE,
  SORTS,
  activeFilters,
  filtersOf,
  queryOf,
  routeQuery,
  type Filters,
} from '@/devices'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/** How many devices the page asks for at a time. */
const PAGE_SIZE = 30
/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

/**
 * Every address that took part in a connection your connected programs reported over the last
 * week: your own devices and the ones on the Internet side, with how many connections were made
 * to each and by each, the ports they used, and the incidents they are in. What the list is
 * narrowed to is in the address of the page, so a link or the back button brings it back as it was.
 */
const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const filters = computed(() => filtersOf(route.query))

function show(next: Partial<Filters>) {
  void router.replace({ query: routeQuery({ ...filters.value, ...next }) })
}

const data = ref<DevicePage | null>(null)
/** The devices on screen: the first page, and any that were asked for after it. */
const items = ref<Device[]>([])
const loadError = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const updatedAt = ref<Date | null>(null)
/** Which load is the newest, so the answer to an older one (for other filters) is dropped. */
let latest = 0

/** Fetches the devices. A refresh in the background (`quiet`) leaves what is on screen as it is
 * until the answer comes, and keeps it if there is none. A `fresh` one starts from the first page,
 * however far the list had been shown. */
async function load(quiet = false, fresh = false) {
  const mine = ++latest
  const asked = filters.value
  if (!quiet) loading.value = true
  try {
    const limit = fresh ? PAGE_SIZE : Math.max(PAGE_SIZE, items.value.length)
    const page = await session.call(() => fetchDevices(queryOf(asked, limit)))
    if (mine !== latest) return
    data.value = page
    items.value = page.items
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine !== latest) return
    loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function loadMore() {
  const mine = ++latest
  loadingMore.value = true
  try {
    const page = await session.call(() =>
      fetchDevices(queryOf(filters.value, PAGE_SIZE, items.value.length)),
    )
    if (mine !== latest) return
    data.value = page
    items.value = [...items.value, ...page.items]
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    loadingMore.value = false
  }
}

// A new choice starts the list again from the top.
watch(filters, () => {
  void load(false, true)
})

const page = computed(() => data.value as DevicePage)
const narrowed = computed(() => activeFilters(filters.value))
const remaining = computed(() => page.value.total - items.value.length)

const description = computed(() => {
  if (!data.value || narrowed.value > 0 || page.value.counts.all === 0) {
    return 'Every address that connected to your network or that your devices connected to.'
  }
  const { all, outside } = page.value.counts
  return `${formatCount(all)} ${all === 1 ? 'device' : 'devices'} this week, ${formatCount(outside)} on the Internet.`
})

/** The scope buttons: every scope, then one for each, each with how many it would show. */
const views = computed(() => [
  { key: 'all', label: 'All', count: page.value.counts.all },
  ...DEVICE_SCOPES.map((key) => ({
    key,
    label: SCOPE[key].label,
    count: page.value.counts[key],
  })),
])

/** What the list says when it has nothing to show. */
const empty = computed(() => {
  if (narrowed.value > 0 || filters.value.scope) {
    return {
      title: 'Nothing matches',
      description: 'No device matches all of these choices.',
      action: 'clear',
    }
  }
  return {
    title: 'No connections yet',
    description: `Devices appear here once a connected program reports a connection, such as a firewall block or an alert. Nothing has been reported in the last ${page.value.days} days.`,
    action: 'integrations',
  }
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)

function pickScope(scope: string | undefined) {
  if (scope) show({ scope: DEVICE_SCOPES.find((each) => each === scope) ?? null })
}

function pickDirection(direction: string) {
  show({ direction: DEVICE_DIRECTIONS.find((each) => each === direction) ?? null })
}

function clearFilters() {
  show({ ...NO_FILTERS, scope: filters.value.scope, sort: filters.value.sort })
}

const search = ref<{ focus: () => void } | null>(null)

/** The slash key goes to the search box from anywhere on the page but another field. */
function onKey(event: KeyboardEvent) {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
  const { target } = event
  if (target instanceof Element && target.closest('input, textarea, select, [contenteditable]')) {
    return
  }
  event.preventDefault()
  search.value?.focus()
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage class="devices">
    <PageHeader title="Devices" :description="description">
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
      data-test="devices-error"
      @retry="load()"
    />
    <template v-else-if="data">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="devices-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <AssetSearch
        ref="search"
        :model-value="filters.q"
        label="Search devices"
        placeholder="Address, name or the asset it is"
        @update:model-value="show({ q: $event })"
      />

      <div class="devices__views">
        <v-btn-toggle
          :model-value="filters.scope ?? 'all'"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Show devices that are"
          data-test="views"
          @update:model-value="pickScope"
        >
          <v-btn
            v-for="view in views"
            :key="view.key"
            :value="view.key"
            :aria-pressed="(filters.scope ?? 'all') === view.key"
            :data-test="`view-${view.key}`"
          >
            {{ view.label }}
            <span
              class="devices__count text-medium-emphasis tabular-nums"
              :data-test="`count-${view.key}`"
              >{{ formatCount(view.count) }}</span
            >
          </v-btn>
        </v-btn-toggle>
      </div>

      <div class="devices__filters">
        <v-select
          label="Connections"
          :items="[
            { value: '', title: 'Any' },
            ...DEVICE_DIRECTIONS.map((key) => ({ value: key, title: DIRECTION[key].label })),
          ]"
          :model-value="filters.direction ?? ''"
          density="comfortable"
          hide-details
          data-test="filter-direction"
          @update:model-value="pickDirection"
        />
        <v-select
          label="Order"
          :items="SORTS"
          item-title="label"
          item-value="value"
          :model-value="filters.sort"
          density="comfortable"
          hide-details
          data-test="filter-sort"
          @update:model-value="show({ sort: $event })"
        />
        <v-btn
          :variant="filters.flagged ? 'tonal' : 'outlined'"
          :color="filters.flagged ? 'primary' : undefined"
          :aria-pressed="filters.flagged"
          density="comfortable"
          data-test="filter-flagged"
          @click="show({ flagged: !filters.flagged })"
        >
          In an incident
        </v-btn>
        <v-btn v-if="narrowed > 0" variant="text" data-test="clear-filters" @click="clearFilters">
          Clear filters
        </v-btn>
      </div>

      <h2 class="sr-only">Devices</h2>
      <ul v-if="items.length" class="devices__list" data-test="device-list">
        <li v-for="item in items" :key="item.address">
          <DeviceCard :device="item" />
        </li>
      </ul>
      <v-card v-else-if="!loading" class="pa-5 pa-sm-6" data-test="devices-empty">
        <EmptyState :title="empty.title" :description="empty.description" :icon="Radar">
          <v-btn
            v-if="empty.action === 'integrations'"
            variant="tonal"
            color="primary"
            :to="{ name: 'integrations' }"
            data-test="empty-integrations"
          >
            See your integrations
          </v-btn>
          <v-btn
            v-else
            variant="tonal"
            color="primary"
            data-test="empty-clear"
            @click="clearFilters"
          >
            Clear filters
          </v-btn>
        </EmptyState>
      </v-card>

      <div v-if="remaining > 0" class="devices__more" data-test="more">
        <p class="text-body-medium text-medium-emphasis">
          Showing {{ formatCount(items.length) }} of {{ formatCount(page.total) }}.
        </p>
        <v-btn variant="outlined" :loading="loadingMore" data-test="show-more" @click="loadMore">
          Show {{ formatCount(Math.min(remaining, PAGE_SIZE)) }} more
        </v-btn>
      </div>

      <p
        v-if="page.capped"
        class="text-body-medium text-medium-emphasis"
        data-test="devices-capped"
      >
        More addresses were seen this week than are read. These are the ones seen most recently.
      </p>
      <p class="text-body-medium text-medium-emphasis" data-test="devices-note">
        A connection here is an event your connected programs reported over the last
        {{ page.days }} days, such as a firewall block or an alert. It is not every packet on the
        network. In means something connected to the device; out means the device connected to
        something.
      </p>
      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="devices-loading" />
  </AppPage>
</template>

<style scoped>
/* Four choices don't fit across a phone, so they scroll sideways rather than wrap into a block. */
.devices__views {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

/* A choice cut off at the edge fades out, so it reads as more to scroll to. */
@media (max-width: 599.98px) {
  .devices__views {
    mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
    scrollbar-width: none;
  }

  .devices__views > :last-child {
    margin-inline-end: 1.5rem;
  }
}

.devices__count {
  margin-inline-start: 0.5rem;
}

.devices__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 20rem));
  align-items: start;
  gap: 0.75rem;
}

.devices__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.devices__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.devices__more p {
  margin: 0;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
