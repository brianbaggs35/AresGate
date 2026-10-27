<script setup lang="ts">
import { ArrowUp, Download, RefreshCw, ScrollText } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

import { ApiError, errorMessage } from '@/api/client'
import type { SearchTerm } from '@/api/incidents'
import { exportAddress, fetchLogs, type LogEvent, type LogPage, type LogSummary } from '@/api/logs'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import LogCards from '@/components/LogCards.vue'
import LogColumns from '@/components/LogColumns.vue'
import LogDrawer from '@/components/LogDrawer.vue'
import LogTable from '@/components/LogTable.vue'
import LogVolume from '@/components/LogVolume.vue'
import PageHeader from '@/components/PageHeader.vue'
import SearchBox from '@/components/SearchBox.vue'
import SearchFacets from '@/components/SearchFacets.vue'
import { formatCount } from '@/format'
import {
  MAX_ROWS,
  PAGE_SIZE,
  SUMMARY_SECONDS,
  TAIL_OVERLAP_SECONDS,
  TAIL_ROUNDS,
  TAIL_SECONDS,
  cursorBefore,
  mergeEvents,
  newOnes,
  readColumns,
  readTimeMode,
  withinRange,
  writeColumns,
  writeTimeMode,
  type ColumnKey,
  type TimeMode,
} from '@/logs'
import { usePolling } from '@/polling'
import {
  LOG_SEARCH,
  groupsOf,
  hasTerm,
  kindChoices,
  severityChoices,
  sourceChoices,
  toggled,
  zone,
} from '@/search'
import { useSessionStore } from '@/stores/session'

/** How far down the page can be scrolled and still count as at the top, where new events are
 * put in at once rather than waited for. */
const TOP_SLACK = 160
/** How often "how long ago" is counted again. */
const CLOCK_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const { mdAndUp: wide } = useDisplay()

/** The search is in the address of the page, so a link or the back button brings it back. */
const q = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''))

function show(text: string) {
  void router.replace({ query: text ? { q: text } : {} })
}

/** The events on screen, the newest first, and the ones that came while the page was scrolled
 * down, waiting to be put above them. */
const items = ref<LogEvent[]>([])
const pending = ref<LogEvent[]>([])
const more = ref(false)
const summary = ref<LogSummary | null>(null)
const terms = ref<SearchTerm[]>([])
/** The search that `terms` are the reading of, which is not the one applied while that is wrong. */
const answered = ref<string | null>(null)
const loaded = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const loadError = ref<string | null>(null)
/** Why the search could not be understood, while it can't. What was on screen stays, with a note. */
const searchError = ref<string | null>(null)
const updatedAt = ref<Date | null>(null)
const live = ref(true)
const now = ref(Date.now())
/** The event that is open in the drawer, and whether the drawer is. */
const selected = ref<LogEvent | null>(null)
const drawer = ref(false)
const columns = ref<ColumnKey[]>(readColumns())
const timeMode = ref<TimeMode>(readTimeMode())
/** Which load is the newest, so the answer to an older one (for another search) is dropped. */
let latest = 0

/** The first page, and how the search is spread. What is on screen stays until the answer comes. */
async function load() {
  const mine = ++latest
  const asked = q.value
  loading.value = true
  try {
    const page: LogPage = await session.call(() =>
      fetchLogs({ q: asked, tz: zone(), limit: PAGE_SIZE }),
    )
    if (mine !== latest) return
    items.value = page.items
    pending.value = []
    more.value = page.more
    summary.value = page.summary
    terms.value = page.terms
    answered.value = asked
    loaded.value = true
    updatedAt.value = new Date()
    loadError.value = null
    searchError.value = null
  } catch (error) {
    if (mine !== latest) return
    if (error instanceof ApiError && error.code === 'invalid' && asked) {
      searchError.value = error.message
      loaded.value = true
    } else {
      loadError.value = errorMessage(error)
    }
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function loadMore() {
  const last = items.value.at(-1)
  if (!last) return
  const mine = ++latest
  loadingMore.value = true
  try {
    const page = await session.call(() =>
      fetchLogs({ q: q.value, tz: zone(), limit: PAGE_SIZE, before: last.cursor, summary: false }),
    )
    if (mine !== latest) return
    // Older events go below, and nothing is trimmed: the person asked for them.
    items.value = mergeEvents(items.value, page.items, Number.POSITIVE_INFINITY)
    more.value = page.more
    updatedAt.value = new Date()
    loadError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    loadingMore.value = false
  }
}

const scrolled = ref(window.scrollY)
const atTop = computed(() => scrolled.value < TOP_SLACK)

function onScroll() {
  scrolled.value = window.scrollY
}

let tailing = false

/** Asks for what is new, from a little before the newest event on screen, in as many rounds as
 * a burst needs. Nothing if the search was changed meanwhile, since the answer is for another. */
async function fetchNewer(asked: string, mine: number): Promise<LogEvent[] | null> {
  const newest = pending.value[0] ?? items.value[0]
  let from = newest ? cursorBefore(newest.cursor, TAIL_OVERLAP_SECONDS) : undefined
  const found: LogEvent[] = []
  for (let round = 0; round < TAIL_ROUNDS; round++) {
    const page = await session.call(() =>
      fetchLogs({ q: asked, tz: zone(), limit: PAGE_SIZE, after: from, summary: false }),
    )
    if (mine !== latest) return null
    found.push(...page.items)
    const top = page.items[0]
    // With nothing yet on screen it was the newest page that came, and `more` means older.
    if (from === undefined || !page.more || !top) break
    from = top.cursor
  }
  return found
}

/** What arrives goes above the events, or waits above the fold if the page is scrolled down. */
function takeIn(found: LogEvent[]) {
  const fresh = newOnes([...pending.value, ...items.value], found)
  if (atTop.value) {
    items.value = mergeEvents(items.value, fresh, MAX_ROWS)
    if (items.value.length >= MAX_ROWS) more.value = true
  } else {
    pending.value = mergeEvents(pending.value, fresh, MAX_ROWS)
  }
  updatedAt.value = new Date()
  loadError.value = null
}

async function tail() {
  if (!live.value || searchError.value || tailing || loading.value || !loaded.value) return
  tailing = true
  const mine = latest
  try {
    const found = await fetchNewer(q.value, mine)
    if (found) takeIn(found)
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    tailing = false
  }
}

/** How the search is spread, asked again now and then, since it changes as events arrive. */
async function refreshSummary() {
  if (!live.value || searchError.value || !loaded.value || loading.value) return
  const mine = latest
  const asked = q.value
  try {
    const page = await session.call(() => fetchLogs({ q: asked, tz: zone(), limit: 1 }))
    if (mine !== latest) return
    summary.value = page.summary
    terms.value = page.terms
  } catch {
    // The events that are on screen are still right; the next time will try again.
  }
}

/** Puts what came while the page was scrolled down above the events, and goes up to them. */
function showPending() {
  items.value = mergeEvents(items.value, pending.value, MAX_ROWS)
  pending.value = []
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: calm ? 'auto' : 'smooth' })
}

// Back at the top by scrolling, there is no reason left to wait.
watch(atTop, (top) => {
  if (top && pending.value.length) {
    items.value = mergeEvents(items.value, pending.value, MAX_ROWS)
    pending.value = []
  }
})

// A new search starts the list again from the top.
watch(q, () => {
  drawer.value = false
  void load()
})

watch(live, (on) => {
  if (on) void tail()
})

const shownTerms = computed(() => (answered.value === q.value ? terms.value : []))
const facetGroups = computed(() => {
  const facets = summary.value?.facets
  if (!facets) return []
  return groupsOf(
    { name: 'Severity', choices: severityChoices(facets.severity, q.value) },
    { name: 'Reported by', choices: sourceChoices(facets.sources, q.value) },
    { name: 'Kind', choices: kindChoices(facets.kinds, q.value) },
  )
})

function toggleFacet(term: string) {
  show(toggled(q.value, term))
}

function pickRange(range: { start: string; end: string }) {
  show(withinRange(q.value, range))
}

/** The drawer's "show events like this": the term goes into the search if it is not there. */
function searchFor(term: string) {
  show(hasTerm(q.value, term) ? q.value : toggled(q.value, term))
  window.scrollTo({ top: 0 })
}

/** The cursor of the event that is open, to mark it in the list. */
const openCursor = computed(() => (drawer.value ? (selected.value as LogEvent).cursor : null))
const position = computed(() =>
  items.value.findIndex(({ cursor }) => cursor === selected.value?.cursor),
)
const hasNewer = computed(() => position.value > 0)
const hasOlder = computed(
  () => position.value >= 0 && (position.value < items.value.length - 1 || more.value),
)

function openEvent(event: LogEvent) {
  selected.value = event
  drawer.value = true
}

async function step(direction: 'older' | 'newer') {
  if (direction === 'older' && position.value === items.value.length - 1) await loadMore()
  const next = items.value[position.value + (direction === 'older' ? 1 : -1)]
  if (next) selected.value = next
}

const empty = computed(() => {
  if (searchError.value) {
    return {
      title: "That search can't be understood",
      description: 'Fix it in the box above, or clear it to see the logs again.',
      clear: true,
    }
  }
  if (q.value) {
    return {
      title: 'Nothing matches',
      description: 'No event matches all of this search. Take a term off, or widen the time.',
      clear: true,
    }
  }
  return {
    title: 'No events yet',
    description:
      'Events appear here as soon as an integration reports something. Connect one, or wait for the next time it is asked.',
    clear: false,
  }
})

const matched = computed(() => {
  const found = summary.value
  if (!found) return null
  const count = formatCount(found.matched)
  if (found.capped) return `The newest ${count} events`
  return `${count} ${found.matched === 1 ? 'event' : 'events'}`
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)

const exporting = computed(() => ({ q: q.value, tz: zone() }))

function chooseColumns(next: ColumnKey[]) {
  columns.value = next
  writeColumns(next)
}

function chooseTime(next: TimeMode) {
  timeMode.value = next
  writeTimeMode(next)
}

const searchBox = ref<{ focus: () => void } | null>(null)

/** The slash key goes to the search box from anywhere on the page but another field, and not
 * while a sheet is over the page. */
function onKey(event: KeyboardEvent) {
  if (drawer.value || event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
  const { target } = event
  if (target instanceof Element && target.closest('input, textarea, select, [contenteditable]')) {
    return
  }
  event.preventDefault()
  searchBox.value?.focus()
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKey)
  window.addEventListener('scroll', onScroll, { passive: true })
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('scroll', onScroll)
})
usePolling(tail, TAIL_SECONDS * 1000)
usePolling(refreshSummary, SUMMARY_SECONDS * 1000)
usePolling(() => {
  now.value = Date.now()
}, CLOCK_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="logs">
    <PageHeader
      title="Logs"
      description="Every event your integrations reported, as they sent it. Search, follow along live, or open one to read its raw record."
    >
      <template #actions>
        <v-menu location="bottom end">
          <template #activator="{ props: activator }">
            <v-btn v-bind="activator" variant="text" :prepend-icon="Download" data-test="export">
              Export
            </v-btn>
          </template>
          <v-card>
            <p class="text-body-medium text-medium-emphasis px-4 pt-3">
              The newest 50,000 that match this search
            </p>
            <!-- The list's own role (list) wants list items, and these are links to files. -->
            <v-list role="menu" aria-label="Download as" tabindex="-1">
              <v-list-item
                role="menuitem"
                :href="exportAddress('csv', exporting)"
                download
                title="CSV"
                subtitle="For a spreadsheet"
                data-test="export-csv"
              />
              <v-list-item
                role="menuitem"
                :href="exportAddress('json', exporting)"
                download
                title="JSON"
                subtitle="With the record each integration sent"
                data-test="export-json"
              />
            </v-list>
          </v-card>
        </v-menu>
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
      v-if="loadError && !loaded"
      :message="loadError"
      :loading="loading"
      data-test="logs-error"
      @retry="load()"
    />
    <template v-else-if="loaded">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="logs-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <SearchBox
        ref="searchBox"
        :kind="LOG_SEARCH"
        :model-value="q"
        :terms="shownTerms"
        :error="searchError"
        @update:model-value="show"
      />

      <SearchFacets :groups="facetGroups" @toggle="toggleFacet" />

      <v-card v-if="summary" class="pa-5 pa-sm-6" data-test="volume-card">
        <LogVolume
          :volume="summary.volume"
          :matched="summary.matched"
          :capped="summary.capped"
          :loading="loading"
          @range="pickRange"
        />
      </v-card>

      <div class="logs__bar">
        <p v-if="matched" class="logs__matched text-title-medium" data-test="matched">
          {{ matched }}
        </p>
        <div class="logs__controls">
          <v-btn
            :variant="live ? 'tonal' : 'outlined'"
            :color="live ? 'success' : undefined"
            :aria-pressed="live"
            data-test="live"
            @click="live = !live"
          >
            <span class="logs__dot" :class="{ 'logs__dot--live': live }" aria-hidden="true" />
            Live
          </v-btn>
          <LogColumns
            v-if="wide"
            :columns="columns"
            :time="timeMode"
            @update:columns="chooseColumns"
            @update:time="chooseTime"
          />
        </div>
      </div>

      <p
        v-if="searchError && items.length"
        class="text-body-medium text-medium-emphasis"
        data-test="search-stale"
      >
        These are the events from the last search that could be understood. Fix the search above to
        update them.
      </p>

      <div v-if="pending.length" class="logs__new">
        <v-btn
          color="primary"
          :prepend-icon="ArrowUp"
          rounded="pill"
          data-test="new-events"
          @click="showPending"
        >
          {{ formatCount(pending.length) }} new {{ pending.length === 1 ? 'event' : 'events' }}
        </v-btn>
      </div>

      <template v-if="items.length">
        <LogTable
          v-if="wide"
          :events="items"
          :columns="columns"
          :time="timeMode"
          :selected="openCursor"
          :now="now"
          @open="openEvent"
        />
        <LogCards v-else :events="items" :selected="openCursor" :now="now" @open="openEvent" />
      </template>
      <v-card v-else class="pa-5 pa-sm-6" data-test="logs-empty">
        <EmptyState :title="empty.title" :description="empty.description" :icon="ScrollText">
          <v-btn
            v-if="empty.clear"
            variant="tonal"
            color="primary"
            data-test="empty-clear"
            @click="show('')"
          >
            Clear the search
          </v-btn>
          <v-btn
            v-else
            variant="tonal"
            color="primary"
            :to="{ name: 'integrations' }"
            data-test="empty-integrations"
          >
            See your integrations
          </v-btn>
        </EmptyState>
      </v-card>

      <div v-if="more && !searchError" class="logs__more" data-test="more">
        <p class="text-body-medium text-medium-emphasis">
          Showing {{ formatCount(items.length)
          }}{{ summary ? ` of ${formatCount(summary.matched)}` : ''
          }}{{ summary?.capped ? '+' : '' }}.
        </p>
        <v-btn variant="outlined" :loading="loadingMore" data-test="show-older" @click="loadMore">
          Show older events
        </v-btn>
      </div>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        <template v-if="live">
          Updated {{ updated }}. This page asks for new events every {{ TAIL_SECONDS }} seconds
          while it is open.
        </template>
        <template v-else>Paused at {{ updated }}. Turn Live back on to follow along.</template>
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="logs-loading" />

    <LogDrawer
      v-model="drawer"
      :event="selected"
      :has-older="hasOlder"
      :has-newer="hasNewer"
      @search="searchFor"
      @step="step"
    />
  </AppPage>
</template>

<style scoped>
.logs__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.logs__matched {
  margin: 0;
}

.logs__controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-inline-start: auto;
}

.logs__dot {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  margin-inline-end: 0.5rem;
  border-radius: 50%;
  background: currentcolor;
  opacity: 0.5;
}

.logs__dot--live {
  opacity: 1;
  animation: logs-pulse 2s ease-in-out infinite;
}

@keyframes logs-pulse {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .logs__dot--live {
    animation: none;
  }
}

/* Waits just under the app bar while the page is scrolled, to take the person back up. It floats
 * over the page so that its coming does not move the events. */
.logs__new {
  position: fixed;
  inset-inline: 0;
  top: calc(var(--v-layout-top, 0px) + 0.75rem);
  z-index: 5;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.logs__new .v-btn {
  pointer-events: auto;
}

.logs__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.logs__more p {
  margin: 0;
}
</style>
