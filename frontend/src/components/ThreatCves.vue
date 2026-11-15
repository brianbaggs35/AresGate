<script setup lang="ts">
import { ChevronRight, Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { RATINGS, fetchCves, type Cve, type CvePage, type Rating } from '@/api/threatCatalog'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import ThreatCveDialog from '@/components/ThreatCveDialog.vue'
import { formatAgo, formatCount, formatDate } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * The vulnerabilities (CVEs) that incidents name, with what NVD says of each: how severe it is,
 * what it is, and whether CISA lists it as exploited in the wild. AresGate asks NVD in the
 * background, one CVE at a time and within NVD's limits, so looking through them asks it nothing.
 * Newest asked first, filtered by rating and by whether it is exploited, searched by identifier,
 * description or weakness; a CVE opens as its report. Where nothing is kept, the empty state says
 * how a CVE gets here. `version` changes when something on the page got an answer, so the list
 * is read again.
 */
const props = defineProps<{ version?: number }>()

const PAGE = 25

const session = useSessionStore()
const page = ref<CvePage | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const typed = ref('')
const text = ref('')
const rating = ref<Rating | null>(null)
const exploited = ref(false)
const shown = ref(PAGE)

const opened = ref<Cve | null>(null)
const reportOpen = ref(false)

const filtered = computed(() => text.value !== '' || rating.value !== null || exploited.value)

/** How many CVEs the text matches, of every rating. */
function kept(found: CvePage): number {
  return RATINGS.reduce((sum, name) => sum + found.counts[name], 0)
}

const LABELS: Record<Rating, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  unrated: 'Not scored',
}

/** The ratings to narrow the list to, each with how many CVEs it has. */
function filters(found: CvePage) {
  return [
    { key: null, label: 'All', count: kept(found) },
    ...RATINGS.map((name) => ({ key: name, label: LABELS[name], count: found.counts[name] })),
  ]
}

async function load() {
  loading.value = true
  error.value = null
  try {
    page.value = await session.call(() =>
      fetchCves({
        q: text.value,
        rating: rating.value,
        exploited: exploited.value,
        limit: shown.value,
      }),
    )
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

function find() {
  text.value = typed.value.trim()
  shown.value = PAGE
  void load()
}

function clear() {
  typed.value = ''
  find()
}

function choose(name: Rating | null) {
  rating.value = name
  shown.value = PAGE
  void load()
}

function toggleExploited() {
  exploited.value = !exploited.value
  shown.value = PAGE
  void load()
}

function showMore() {
  shown.value += PAGE
  void load()
}

function open(item: Cve) {
  opened.value = item
  reportOpen.value = true
}

/** A sentence a screen reader says for a row, since the row is one button. */
function describe(item: Cve): string {
  const how = item.rating === 'unrated' ? 'not scored' : `${LABELS[item.rating]}, ${item.score}`
  return `${item.cve_id}, ${how}${item.exploited ? ', exploited in the wild' : ''}. Open its report.`
}

watch(() => props.version, load)
onMounted(load)
</script>

<template>
  <SectionCard
    title="Vulnerabilities"
    description="The CVEs that incidents name, with what NVD says of each: how severe it is, and whether CISA lists it as exploited in the wild. AresGate asks NVD in the background, one at a time and within its limits, so looking through them asks it nothing. An answer nobody has looked at for the time set under Retention is removed."
    data-test="threat-cves"
  >
    <LoadError
      v-if="error && !page"
      :message="error"
      :loading="loading"
      retry-test-id="cves-retry"
      data-test="cves-error"
      @retry="load"
    />

    <v-skeleton-loader v-else-if="!page" type="list-item-two-line@3" data-test="cves-loading" />

    <EmptyState
      v-else-if="!kept(page) && !filtered"
      title="No CVEs yet"
      description="When an incident names a CVE, AresGate asks NVD about it in the background once NVD is connected, and the answer shows up here."
      data-test="cves-empty"
    >
      <v-btn :to="{ name: 'integrations' }" variant="tonal" data-test="cves-set-up">
        Go to Integrations
      </v-btn>
    </EmptyState>

    <template v-else>
      <form novalidate class="cves__find" data-test="cves-form" @submit.prevent="find">
        <v-text-field
          v-model="typed"
          label="Find a CVE"
          placeholder="An identifier, a word from the description or a weakness"
          :prepend-inner-icon="Search"
          autocomplete="off"
          spellcheck="false"
          density="comfortable"
          hide-details
          clearable
          data-test="cves-text"
          @click:clear="clear"
        />
        <v-btn type="submit" variant="tonal" :loading="loading" data-test="cves-find">Find</v-btn>
      </form>

      <fieldset class="cves__filters" data-test="cves-filters">
        <legend class="cves__legend">Rating</legend>
        <v-btn
          v-for="filter in filters(page)"
          :key="filter.key ?? 'all'"
          :variant="rating === filter.key ? 'flat' : 'outlined'"
          :color="rating === filter.key ? 'primary' : undefined"
          :aria-pressed="rating === filter.key"
          size="small"
          rounded="pill"
          :data-test="`cves-filter-${filter.key ?? 'all'}`"
          @click="choose(filter.key)"
        >
          {{ filter.label }} {{ formatCount(filter.count) }}
        </v-btn>
        <v-btn
          :variant="exploited ? 'flat' : 'outlined'"
          :color="exploited ? 'error' : undefined"
          :aria-pressed="exploited"
          size="small"
          rounded="pill"
          data-test="cves-filter-exploited"
          @click="toggleExploited"
        >
          Exploited in the wild {{ formatCount(page.counts.exploited) }}
        </v-btn>
      </fieldset>

      <v-alert
        v-if="error"
        type="error"
        variant="tonal"
        class="cves__alert"
        data-test="cves-problem"
      >
        {{ error }}
      </v-alert>

      <p
        v-if="!page.items.length"
        class="text-body-medium text-medium-emphasis cves__none"
        data-test="cves-none"
      >
        Nothing kept matches.
      </p>

      <ul v-else class="cves__list" data-test="cves-list">
        <li v-for="item in page.items" :key="item.cve_id">
          <button
            type="button"
            class="cves__row"
            :aria-label="describe(item)"
            :data-rating="item.rating"
            data-test="cves-row"
            @click="open(item)"
          >
            <span class="cves__rating">
              <SeverityChip v-if="item.rating !== 'unrated'" :severity="item.rating" />
              <v-chip v-else variant="tonal" size="small" data-test="cves-unrated">
                {{ item.state === 'unknown' ? 'Unknown to NVD' : 'Not scored' }}
              </v-chip>
            </span>
            <span class="cves__id" data-test="cves-id">{{ item.cve_id }}</span>
            <span v-if="item.description" class="cves__description" data-test="cves-description">
              {{ item.description }}
            </span>
            <span class="cves__facts text-body-small text-medium-emphasis">
              <v-chip
                v-if="item.exploited"
                color="error"
                variant="flat"
                size="x-small"
                data-test="cves-exploited"
              >
                Exploited in the wild
              </v-chip>
              <span v-if="item.score !== null" data-test="cves-score">
                CVSS {{ item.score.toFixed(1) }}
              </span>
              <span v-if="item.published_at" data-test="cves-published">
                Published {{ formatDate(item.published_at.slice(0, 10)) }}
              </span>
              <span data-test="cves-checked">Asked {{ formatAgo(item.checked_at) }}</span>
            </span>
            <ChevronRight :size="18" aria-hidden="true" class="cves__open" />
          </button>
        </li>
      </ul>

      <div v-if="page.total > page.items.length" class="cves__more">
        <v-btn variant="text" :loading="loading" data-test="cves-more" @click="showMore">
          Show more ({{ formatCount(page.total - page.items.length) }} left)
        </v-btn>
      </div>

      <p class="text-body-small text-medium-emphasis cves__notice" data-test="cves-notice">
        {{ page.notice }}
      </p>
    </template>

    <ThreatCveDialog
      v-if="opened && page"
      v-model="reportOpen"
      :cve="opened"
      :notice="page.notice"
    />
  </SectionCard>
</template>

<style scoped>
.cves__find {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.cves__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

/* Read out as the name of the group, and not shown. */
.cves__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.cves__alert {
  margin-top: 0.75rem;
}

.cves__none {
  margin: 1rem 0 0;
}

.cves__list {
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.cves__list li + li {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.cves__row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas:
    'rating id open'
    'description description open'
    'facts facts open';
  align-items: center;
  gap: 0.25rem 0.75rem;
  width: 100%;
  padding: 0.75rem 0.5rem;
  border: 0;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.cves__row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.cves__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.cves__rating {
  grid-area: rating;
  pointer-events: none;
}

.cves__id {
  grid-area: id;
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

/* The first lines say what it is, and the report has the rest. */
.cves__description {
  grid-area: description;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.cves__facts {
  grid-area: facts;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.125rem 1rem;
}

.cves__open {
  grid-area: open;
  opacity: 0.6;
}

.cves__more {
  display: flex;
  justify-content: center;
  margin-top: 0.5rem;
}

.cves__notice {
  margin: 0.75rem 0 0;
}
</style>
