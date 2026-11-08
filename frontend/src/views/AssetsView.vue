<script setup lang="ts">
import { MonitorSmartphone, RefreshCw } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { ASSET_STATUSES, fetchAssets, type Asset, type AssetPage } from '@/api/assets'
import AppPage from '@/components/AppPage.vue'
import AssetCard from '@/components/AssetCard.vue'
import AssetSearch from '@/components/AssetSearch.vue'
import AssetSuppliers from '@/components/AssetSuppliers.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  NO_FILTERS,
  SORTS,
  STATUS,
  activeFilters,
  filtersOf,
  queryOf,
  routeQuery,
  type Filters,
} from '@/inventory'
import { formatCount, formatDateTime, formatList } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/** How many assets the page asks for at a time. */
const PAGE_SIZE = 30
/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

/**
 * Every device the connected programs can see, as one list: OPNsense from its ARP table and DHCP
 * leases, ntopng from its active hosts, Wazuh from its agents. What they say about one device is
 * merged, and each shows which programs listed it. What the list is narrowed to is in the address
 * of the page, so a link or the back button brings it back as it was.
 */
const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const filters = computed(() => filtersOf(route.query))

function show(next: Partial<Filters>) {
  void router.replace({ query: routeQuery({ ...filters.value, ...next }) })
}

const data = ref<AssetPage | null>(null)
/** The assets on screen: the first page, and any that were asked for after it. */
const items = ref<Asset[]>([])
const loadError = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const updatedAt = ref<Date | null>(null)
/** Which load is the newest, so the answer to an older one (for other filters) is dropped. */
let latest = 0

/** Fetches the assets. A refresh in the background (`quiet`) leaves what is on screen as it is
 * until the answer comes, and keeps it if there is none. A `fresh` one starts from the first page,
 * however far the list had been shown. */
async function load(quiet = false, fresh = false) {
  const mine = ++latest
  const asked = filters.value
  if (!quiet) loading.value = true
  try {
    const limit = fresh ? PAGE_SIZE : Math.max(PAGE_SIZE, items.value.length)
    const page = await session.call(() => fetchAssets(queryOf(asked, limit)))
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
      fetchAssets(queryOf(filters.value, PAGE_SIZE, items.value.length)),
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

const page = computed(() => data.value as AssetPage)
const narrowed = computed(() => activeFilters(filters.value))
const remaining = computed(() => page.value.total - items.value.length)
const connected = computed(() => page.value.suppliers.filter((item) => item.connected))
/** Where the listing programs say they got the assets from, to filter by. */
const listing = computed(() =>
  page.value.suppliers.filter(
    (item) => item.assets > 0 || filters.value.sources.includes(item.key),
  ),
)
const interfaceNames = computed(
  () => new Map(page.value.interfaces.map((item) => [item.id, item.name])),
)

function interfacesOf(asset: Asset): string[] {
  return asset.interfaces.flatMap((id) => interfaceNames.value.get(id) ?? [])
}

/** What is left out for being on the Internet side: the provider's, not the home's. */
const outsideNote = computed(() => {
  const { outside } = page.value
  return outside === 1
    ? "1 device on the Internet side is not listed, such as your provider's equipment."
    : `${formatCount(outside)} devices on the Internet side are not listed, such as your provider's equipment.`
})

const description = computed(() => {
  if (!data.value) return 'Every device your connected programs can see, as one list.'
  const { all, online } = page.value.counts
  if (narrowed.value > 0 || all === 0)
    return 'Every device your connected programs can see, as one list.'
  return `${formatCount(all)} ${all === 1 ? 'asset' : 'assets'}, ${formatCount(online)} online now.`
})

/** The state buttons: every state, then one for each, each with how many it would show. */
const views = computed(() => [
  { key: 'all', label: 'All', count: page.value.counts.all },
  ...ASSET_STATUSES.map((key) => ({
    key,
    label: STATUS[key].label,
    count: page.value.counts[key],
  })),
])

/** What the list says when it has nothing to show, and what to offer. */
const empty = computed(() => {
  const { status } = filters.value
  const { all } = page.value.counts
  if (narrowed.value > 0) {
    return {
      title: 'Nothing matches',
      description: 'No asset matches all of these choices.',
      action: 'clear',
    }
  }
  if (status && all > 0) {
    return {
      title: 'None here',
      description: `No asset is in the \u201c${STATUS[status].label}\u201d state. ${formatCount(all)} in all.`,
      action: 'all',
    }
  }
  if (connected.value.length === 0) {
    return {
      title: 'No devices yet',
      description:
        'Devices appear here once a program that can list them is connected: OPNsense lists them from its ARP table and DHCP leases, ntopng from its active hosts and Wazuh from its agents.',
      action: 'integrations',
    }
  }
  return {
    title: 'Waiting for the first devices',
    description: `${formatList(connected.value.map((item) => item.name))} ${connected.value.length === 1 ? 'is' : 'are'} connected, but nothing has listed a device yet. They are read every minute. The Status page says if a collector is failing.`,
    action: 'status',
  }
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)

function pickStatus(status: string | undefined) {
  if (status) show({ status: ASSET_STATUSES.find((each) => each === status) ?? null })
}

function toggleSource(key: string) {
  const sources = filters.value.sources
  show({
    sources: sources.includes(key) ? sources.filter((each) => each !== key) : [...sources, key],
  })
}

function clearFilters() {
  show({ ...NO_FILTERS, status: filters.value.status, sort: filters.value.sort })
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
  <AppPage class="assets">
    <PageHeader title="Assets" :description="description">
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
      data-test="assets-error"
      @retry="load()"
    />
    <template v-else-if="data">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="assets-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <AssetSearch
        ref="search"
        :model-value="filters.q"
        @update:model-value="show({ q: $event })"
      />

      <div class="assets__views">
        <v-btn-toggle
          :model-value="filters.status ?? 'all'"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Show assets that are"
          data-test="views"
          @update:model-value="pickStatus"
        >
          <v-btn
            v-for="view in views"
            :key="view.key"
            :value="view.key"
            :aria-pressed="(filters.status ?? 'all') === view.key"
            :data-test="`view-${view.key}`"
          >
            {{ view.label }}
            <span
              class="assets__count text-medium-emphasis tabular-nums"
              :data-test="`count-${view.key}`"
              >{{ formatCount(view.count) }}</span
            >
          </v-btn>
        </v-btn-toggle>
      </div>

      <div class="assets__filters">
        <v-select
          v-if="page.interfaces.length"
          label="Interface"
          :items="[{ id: 0, name: 'Any interface' }, ...page.interfaces]"
          item-title="name"
          item-value="id"
          :model-value="filters.interface ?? 0"
          density="comfortable"
          hide-details
          data-test="filter-interface"
          @update:model-value="show({ interface: $event || null })"
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
      </div>

      <fieldset class="assets__toggles">
        <legend class="sr-only">Narrow the list</legend>
        <v-btn
          v-for="source in listing"
          :key="source.key"
          :variant="filters.sources.includes(source.key) ? 'tonal' : 'outlined'"
          :color="filters.sources.includes(source.key) ? 'primary' : undefined"
          :aria-pressed="filters.sources.includes(source.key)"
          density="comfortable"
          :data-test="`filter-source-${source.key}`"
          @click="toggleSource(source.key)"
        >
          Listed by {{ source.name }}
          <span class="assets__count text-medium-emphasis tabular-nums">{{
            formatCount(source.assets)
          }}</span>
        </v-btn>
        <v-btn
          :variant="filters.new ? 'tonal' : 'outlined'"
          :color="filters.new ? 'primary' : undefined"
          :aria-pressed="filters.new"
          density="comfortable"
          data-test="filter-new"
          @click="show({ new: !filters.new })"
        >
          New this week
          <span class="assets__count text-medium-emphasis tabular-nums">{{
            formatCount(page.new)
          }}</span>
        </v-btn>
        <v-btn
          :variant="filters.unidentified ? 'tonal' : 'outlined'"
          :color="filters.unidentified ? 'primary' : undefined"
          :aria-pressed="filters.unidentified"
          density="comfortable"
          data-test="filter-unidentified"
          @click="show({ unidentified: !filters.unidentified })"
        >
          Not identified
          <span class="assets__count text-medium-emphasis tabular-nums">{{
            formatCount(page.unidentified)
          }}</span>
        </v-btn>
        <v-btn v-if="narrowed > 0" variant="text" data-test="clear-filters" @click="clearFilters">
          Clear filters
        </v-btn>
      </fieldset>

      <h2 class="sr-only">Assets</h2>
      <ul v-if="items.length" class="assets__list" data-test="asset-list">
        <li v-for="item in items" :key="item.key">
          <AssetCard :asset="item" :interfaces="interfacesOf(item)" />
        </li>
      </ul>
      <v-card v-else-if="!loading" class="pa-5 pa-sm-6" data-test="assets-empty">
        <EmptyState :title="empty.title" :description="empty.description" :icon="MonitorSmartphone">
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
            v-else-if="empty.action === 'status'"
            variant="tonal"
            color="primary"
            :to="{ name: 'status' }"
            data-test="empty-status"
          >
            Open Status
          </v-btn>
          <v-btn
            v-else-if="empty.action === 'clear'"
            variant="tonal"
            color="primary"
            data-test="empty-clear"
            @click="clearFilters"
          >
            Clear filters
          </v-btn>
          <v-btn
            v-else
            variant="tonal"
            color="primary"
            data-test="empty-all"
            @click="pickStatus('all')"
          >
            Show every asset
          </v-btn>
        </EmptyState>
      </v-card>

      <div v-if="remaining > 0" class="assets__more" data-test="more">
        <p class="text-body-medium text-medium-emphasis">
          Showing {{ formatCount(items.length) }} of {{ formatCount(page.total) }}.
        </p>
        <v-btn variant="outlined" :loading="loadingMore" data-test="show-more" @click="loadMore">
          Show {{ formatCount(Math.min(remaining, PAGE_SIZE)) }} more
        </v-btn>
      </div>

      <AssetSuppliers :suppliers="page.suppliers" />

      <p
        v-if="page.outside > 0"
        class="text-body-medium text-medium-emphasis"
        data-test="assets-outside"
      >
        {{ outsideNote }} Your firewall's own addresses stay listed.
      </p>

      <p
        v-if="page.watching_since"
        class="text-body-medium text-medium-emphasis"
        data-test="assets-note"
      >
        New means first listed in the last 7 days. The devices found on the first day, from
        {{ formatDateTime(page.watching_since) }}, are the network as it was and are not counted as
        new.
      </p>
      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="assets-loading" />
  </AppPage>
</template>

<style scoped>
/* Four choices don't fit across a phone, so they scroll sideways rather than wrap into a block. */
.assets__views {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

/* A choice cut off at the edge fades out, so it reads as more to scroll to. */
@media (max-width: 599.98px) {
  .assets__views {
    mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
    scrollbar-width: none;
  }

  .assets__views > :last-child {
    margin-inline-end: 1.5rem;
  }
}

.assets__count {
  margin-inline-start: 0.5rem;
}

.assets__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 20rem));
  align-items: start;
  gap: 0.75rem;
}

.assets__toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  min-inline-size: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.assets__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.assets__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.assets__more p {
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
