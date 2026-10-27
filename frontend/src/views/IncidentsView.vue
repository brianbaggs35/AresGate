<script setup lang="ts">
import { RefreshCw, Search, ShieldCheck } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'

import { errorMessage } from '@/api/client'
import { fetchIncidents, type Incident, type IncidentPage } from '@/api/incidents'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import IncidentCard from '@/components/IncidentCard.vue'
import JudgedNotice from '@/components/JudgedNotice.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import { formatCount } from '@/format'
import {
  CONFIDENCE_FILTERS,
  DEFAULT_VIEW,
  SEVERITY_FILTERS,
  VIEWS,
  activeFilters,
  countIn,
  isAddress,
  queryOf,
  type Filters,
  type ViewKey,
} from '@/incidents'
import { usePolling } from '@/polling'
import { SEVERITIES, type Severity } from '@/severity'
import { useSessionStore } from '@/stores/session'
import type { Judged } from '@/verdicts'

/** How many incidents the page asks for at a time. */
const PAGE_SIZE = 25
/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

/** What the list is narrowed to is in the address of the page, so a link or the back button
 * brings it back as it was. Anything in it that isn't one of the choices is ignored. */
function filtersOf(query: LocationQuery): Filters {
  const one = (name: string) => {
    const value = query[name]
    return typeof value === 'string' ? value : ''
  }
  const view = VIEWS.find(({ key }) => key === one('view'))?.key ?? DEFAULT_VIEW
  const severity = SEVERITIES.find((level) => level === one('severity')) ?? null
  const confidence = CONFIDENCE_FILTERS.find(({ value }) => value.toString() === one('confidence'))
  return {
    view,
    severity,
    confidence: confidence?.value ?? 0,
    address: one('address'),
    quieted: one('quieted') === '1',
  }
}

const filters = computed(() => filtersOf(route.query))

/** The address as it is typed, which counts once it is whole. */
const typed = ref(filters.value.address)
const partial = computed(() => typed.value.trim() !== '' && !isAddress(typed.value.trim()))

function show(next: Partial<Filters>) {
  const merged = { ...filters.value, ...next }
  const query: Record<string, string> = {}
  if (merged.view !== DEFAULT_VIEW) query.view = merged.view
  if (merged.severity) query.severity = merged.severity
  if (merged.confidence) query.confidence = merged.confidence.toString()
  if (merged.address) query.address = merged.address
  if (merged.quieted) query.quieted = '1'
  void router.replace({ query })
}

function typeAddress(text: string | null) {
  typed.value = text ?? ''
  const whole = isAddress(typed.value.trim()) ? typed.value.trim() : ''
  if (whole !== filters.value.address) show({ address: whole })
}

function clearFilters() {
  typed.value = ''
  show({ severity: null, confidence: 0, address: '', quieted: false })
}

const data = ref<IncidentPage | null>(null)
/** The incidents on screen: the first page, and any that were asked for after it. */
const items = ref<Incident[]>([])
const loadError = ref<string | null>(null)
/** Whether a load that someone asked for is under way. */
const loading = ref(false)
const loadingMore = ref(false)
const updatedAt = ref<Date | null>(null)
/** Which load is the newest, so the answer to an older one (for other filters) is dropped. */
let latest = 0

/** Fetches the incidents. A refresh in the background (`quiet`) leaves what is on screen as it
 * is until the answer comes, and keeps it if there is none. */
async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const limit = Math.max(PAGE_SIZE, items.value.length)
    const page = await session.call(() => fetchIncidents(queryOf(filters.value, limit)))
    if (mine !== latest) return
    data.value = page
    items.value = page.items
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function loadMore() {
  const mine = ++latest
  loadingMore.value = true
  try {
    const page = await session.call(() =>
      fetchIncidents({ ...queryOf(filters.value, PAGE_SIZE), offset: items.value.length }),
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
  items.value = []
  void load()
})

const counts = computed(() => (data.value as IncidentPage).counts)
const everything = computed(() => countIn('all', counts.value))
const narrowed = computed(() => activeFilters(filters.value))
const remaining = computed(() => (data.value as IncidentPage).total - items.value.length)
/** How many incidents the owner quieted that the list would include if asked. */
const quieted = computed(() => (data.value as IncidentPage).quieted)

/** What the list says when it has nothing to show. */
const empty = computed(() => {
  if (everything.value === 0 && quieted.value > 0 && !filters.value.quieted) {
    return {
      title: 'Nothing needs you',
      description: `Every incident is one you called not suspicious or low priority. ${formatCount(quieted.value)} ${quieted.value === 1 ? 'is' : 'are'} hidden.`,
      action: 'quieted',
    }
  }
  if (everything.value === 0) {
    return {
      title: 'No incidents yet',
      description:
        'Incidents appear here when alerts and bans from your integrations are grouped by what they are about. Nothing has needed grouping yet.',
      action: 'integrations',
    }
  }
  if (narrowed.value > 0) {
    return {
      title: 'Nothing matches',
      description: 'No incident matches all of these choices.',
      action: 'clear',
    }
  }
  const { view } = filters.value
  return {
    title: view === 'active' ? 'Nothing needs you' : 'None here',
    description:
      view === 'active'
        ? `Every incident is resolved or dismissed. ${formatCount(everything.value)} in all.`
        : `No incident has this status. ${formatCount(everything.value)} in all.`,
    action: 'all',
  }
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)

const notice = ref<{ show: (verdict: Judged) => void } | null>(null)

/** A card gave a verdict: say so, and ask again, since it can leave the list. */
function judged(verdict: Judged) {
  notice.value?.show(verdict)
  void load(true)
}

function pickView(view: ViewKey | undefined) {
  if (view) show({ view })
}

function pickSeverity(severity: Severity | null) {
  show({ severity })
}

function pickConfidence(confidence: number) {
  show({ confidence })
}

function pickQuieted(include: boolean | null) {
  show({ quieted: include === true })
}

onMounted(load)
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage class="incidents">
    <PageHeader
      title="Incidents"
      description="Alerts and bans from every integration that belong together, so you see one story instead of many rows."
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
      data-test="incidents-error"
      @retry="load()"
    />
    <template v-else-if="data">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="incidents-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <div class="incidents__views">
        <v-btn-toggle
          :model-value="filters.view"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Show incidents that are"
          data-test="views"
          @update:model-value="pickView"
        >
          <v-btn
            v-for="view in VIEWS"
            :key="view.key"
            :value="view.key"
            :data-test="`view-${view.key}`"
          >
            {{ view.label }}
            <span
              class="incidents__count text-medium-emphasis tabular-nums"
              :data-test="`count-${view.key}`"
              >{{ formatCount(countIn(view.key, counts)) }}</span
            >
          </v-btn>
        </v-btn-toggle>
      </div>

      <div class="incidents__filters">
        <v-select
          label="Severity"
          :items="SEVERITY_FILTERS"
          item-title="label"
          item-value="value"
          :model-value="filters.severity"
          hide-details
          data-test="filter-severity"
          @update:model-value="pickSeverity"
        />
        <v-select
          label="Confidence"
          :items="CONFIDENCE_FILTERS"
          item-title="label"
          item-value="value"
          :model-value="filters.confidence"
          hide-details
          data-test="filter-confidence"
          @update:model-value="pickConfidence"
        />
        <v-text-field
          label="Address"
          placeholder="93.184.216.34"
          :prepend-inner-icon="Search"
          :model-value="typed"
          clearable
          :hide-details="!partial"
          :hint="partial ? 'Type a whole IP address to look for it.' : undefined"
          persistent-hint
          autocomplete="off"
          spellcheck="false"
          data-test="filter-address"
          @update:model-value="typeAddress"
        />
      </div>
      <div v-if="narrowed > 0 || quieted > 0" class="incidents__options">
        <v-btn v-if="narrowed > 0" variant="text" data-test="clear-filters" @click="clearFilters">
          Clear filters
        </v-btn>
        <v-switch
          v-if="quieted > 0"
          :model-value="filters.quieted"
          :label="`Show ${formatCount(quieted)} quieted by your verdicts`"
          color="primary"
          density="comfortable"
          hide-details
          class="incidents__quieted"
          data-test="filter-quieted"
          @update:model-value="pickQuieted"
        />
      </div>

      <ul v-if="items.length" class="incidents__list" data-test="incident-list">
        <li v-for="item in items" :key="item.id">
          <IncidentCard :incident="item" @judged="judged" />
        </li>
      </ul>
      <v-card v-else class="pa-5 pa-sm-6" data-test="incidents-empty">
        <EmptyState :title="empty.title" :description="empty.description" :icon="ShieldCheck">
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
            v-else-if="empty.action === 'quieted'"
            variant="tonal"
            color="primary"
            data-test="empty-quieted"
            @click="pickQuieted(true)"
          >
            Show them
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
            @click="pickView('all')"
          >
            Show all incidents
          </v-btn>
        </EmptyState>
      </v-card>

      <div v-if="remaining > 0" class="incidents__more" data-test="more">
        <p class="text-body-medium text-medium-emphasis">
          Showing {{ formatCount(items.length) }} of {{ formatCount(data.total) }}.
        </p>
        <v-btn variant="outlined" :loading="loadingMore" data-test="show-more" @click="loadMore">
          Show {{ formatCount(Math.min(remaining, PAGE_SIZE)) }} more
        </v-btn>
      </div>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="incidents-loading" />

    <JudgedNotice ref="notice" @undone="load(true)" />
  </AppPage>
</template>

<style scoped>
/* Six choices don't fit across a phone, so they scroll sideways rather than wrap into a block. */
.incidents__views {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

/* A choice cut off at the edge fades out, so it reads as more to scroll to; the last one has
   room at its end to scroll clear of the fade. */
@media (max-width: 599.98px) {
  .incidents__views {
    mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
    scrollbar-width: none;
  }

  .incidents__views > :last-child {
    margin-inline-end: 1.5rem;
  }
}

.incidents__count {
  margin-inline-start: 0.5rem;
}

.incidents__filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: 0.75rem;
}

.incidents__filters > :nth-child(3) {
  grid-column: 1 / -1;
}

.incidents__options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0 1rem;
  margin-top: -0.75rem;
}

.incidents__quieted {
  margin-inline-start: auto;
}

.incidents__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.incidents__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.incidents__more p {
  margin: 0;
}

@media (min-width: 720px) {
  .incidents__filters {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr);
  }

  .incidents__filters > :nth-child(3) {
    grid-column: auto;
  }
}
</style>
