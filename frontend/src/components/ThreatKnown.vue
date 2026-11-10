<script setup lang="ts">
import { ChevronRight, Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchKnownThreats,
  searchThreatIntel,
  type Judgement,
  type KnownPage,
  type Lookup,
} from '@/api/threatIntel'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { formatAgo, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { JUDGEMENT, JUDGEMENTS, KIND } from '@/threatIntel'

/**
 * What AresGate knows from threat intelligence: every answer it has kept, newest first, whether a
 * search or a background lookup asked for it. Looking through them asks VirusTotal nothing. An
 * answer opens as the report it was, and Check again asks VirusTotal for a newer one, which counts
 * toward its limits as a search does. `version` changes when something on the page got an answer,
 * so the list is read again.
 */
const props = defineProps<{ version?: number }>()
const emit = defineEmits<{ refused: [] }>()

const PAGE = 25

const session = useSessionStore()
const page = ref<KnownPage | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const typed = ref('')
const text = ref('')
const judgement = ref<Judgement | null>(null)
const shown = ref(PAGE)

const opened = ref<Lookup | null>(null)
const reportOpen = ref(false)
const checking = ref(false)
const problem = ref<string | null>(null)

const filtered = computed(() => text.value !== '' || judgement.value !== null)

/** How many answers the text matches, of every judgement. */
function kept(found: KnownPage): number {
  return JUDGEMENTS.reduce((sum, name) => sum + found.counts[name], 0)
}

/** The judgements to narrow the list to, each with how many answers it has. */
function filters(found: KnownPage) {
  return [
    { key: null, label: 'All', count: kept(found) },
    ...JUDGEMENTS.map((name) => ({
      key: name,
      label: JUDGEMENT[name].short,
      count: found.counts[name],
    })),
  ]
}

async function load() {
  loading.value = true
  error.value = null
  try {
    page.value = await session.call(() =>
      fetchKnownThreats({ q: text.value, judgement: judgement.value, limit: shown.value }),
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

function choose(name: Judgement | null) {
  judgement.value = name
  shown.value = PAGE
  void load()
}

function showMore() {
  shown.value += PAGE
  void load()
}

function open(item: Lookup) {
  opened.value = item
  problem.value = null
  reportOpen.value = true
}

/** A sentence a screen reader says for a row, since the row is one button. */
function describe(item: Lookup): string {
  return `${item.subject}, ${KIND[item.kind]}, ${JUDGEMENT[item.judgement].short}. Open its report.`
}

/** How many engines flagged it, of how many gave a verdict. */
function tally(item: Lookup): string {
  if (item.judgement === 'unknown') return 'No report'
  const engines = item.malicious + item.suspicious + item.harmless + item.undetected
  return `${formatCount(item.malicious + item.suspicious)} of ${formatCount(engines)} flagged`
}

/** Asks VirusTotal again about the answer that is open, and shows what came back. */
async function checkAgain() {
  const item = opened.value
  if (!item || checking.value) return
  checking.value = true
  problem.value = null
  try {
    opened.value = await session.change((token) => searchThreatIntel(item.subject, token, true))
    if (opened.value.notice) emit('refused')
    await load()
  } catch (checkError) {
    problem.value = errorMessage(checkError)
    reportOpen.value = false
    emit('refused')
  } finally {
    checking.value = false
  }
}

watch(() => props.version, load)
onMounted(load)
</script>

<template>
  <SectionCard
    title="What AresGate knows"
    description="Every answer from threat intelligence is kept here, whether you searched for it or AresGate looked it up for an incident. Looking through them asks VirusTotal nothing. An answer is checked again once it is no longer fresh: after two days if it was flagged or had no report, and after a week if no engine flagged it."
    data-test="threat-known"
  >
    <LoadError
      v-if="error && !page"
      :message="error"
      :loading="loading"
      retry-test-id="threat-known-retry"
      data-test="threat-known-error"
      @retry="load"
    />

    <v-skeleton-loader v-else-if="!page" type="list-item-two-line@3" data-test="known-loading" />

    <EmptyState
      v-else-if="!kept(page) && !filtered"
      title="Nothing is kept yet"
      description="The first answer from a search, or from a lookup about an incident's address, shows up here."
      data-test="known-empty"
    />

    <template v-else>
      <form novalidate class="known__find" data-test="known-form" @submit.prevent="find">
        <v-text-field
          v-model="typed"
          label="Find in what is kept"
          placeholder="Part of an address, a name or an owner"
          :prepend-inner-icon="Search"
          autocomplete="off"
          spellcheck="false"
          density="comfortable"
          hide-details
          clearable
          data-test="known-text"
          @click:clear="clear"
        />
        <v-btn type="submit" variant="tonal" :loading="loading" data-test="known-find">Find</v-btn>
      </form>

      <div class="known__filters" role="group" aria-label="Judgement" data-test="known-filters">
        <v-btn
          v-for="filter in filters(page)"
          :key="filter.key ?? 'all'"
          :variant="judgement === filter.key ? 'flat' : 'outlined'"
          :color="judgement === filter.key ? 'primary' : undefined"
          :aria-pressed="judgement === filter.key"
          size="small"
          rounded="pill"
          :data-test="`known-filter-${filter.key ?? 'all'}`"
          @click="choose(filter.key)"
        >
          {{ filter.label }} {{ formatCount(filter.count) }}
        </v-btn>
      </div>

      <v-alert
        v-if="error ?? problem"
        type="error"
        variant="tonal"
        class="known__alert"
        data-test="known-problem"
      >
        {{ error ?? problem }}
      </v-alert>

      <p
        v-if="!page.items.length"
        class="text-body-medium text-medium-emphasis known__none"
        data-test="known-none"
      >
        Nothing kept matches.
      </p>

      <ul v-else class="known__list" data-test="known-list">
        <li v-for="item in page.items" :key="item.link">
          <button
            type="button"
            class="known__row"
            :aria-label="describe(item)"
            :data-judgement="item.judgement"
            data-test="known-row"
            @click="open(item)"
          >
            <v-chip
              :color="JUDGEMENT[item.judgement].color"
              :prepend-icon="JUDGEMENT[item.judgement].icon"
              variant="tonal"
              size="small"
              class="known__judgement"
            >
              {{ JUDGEMENT[item.judgement].short }}
            </v-chip>
            <span class="known__subject" data-test="known-subject">{{ item.subject }}</span>
            <span class="known__facts text-body-small text-medium-emphasis">
              <span>{{ KIND[item.kind] }}</span>
              <span data-test="known-tally">{{ tally(item) }}</span>
              <span data-test="known-checked">Checked {{ formatAgo(item.checked_at) }}</span>
              <span v-if="item.stale" data-test="known-stale">Due to be checked again</span>
            </span>
            <ChevronRight :size="18" aria-hidden="true" class="known__open" />
          </button>
        </li>
      </ul>

      <div v-if="page.total > page.items.length" class="known__more">
        <v-btn variant="text" :loading="loading" data-test="known-more" @click="showMore">
          Show more ({{ formatCount(page.total - page.items.length) }} left)
        </v-btn>
      </div>
    </template>

    <ThreatReportDialog
      v-if="opened"
      v-model="reportOpen"
      :lookup="opened"
      :busy="checking"
      @refresh="checkAgain"
    />
  </SectionCard>
</template>

<style scoped>
.known__find {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.known__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.known__alert {
  margin-top: 0.75rem;
}

.known__none {
  margin: 1rem 0 0;
}

.known__list {
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.known__list li + li {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.known__row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas:
    'judgement subject open'
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

.known__row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.known__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.known__judgement {
  grid-area: judgement;
  pointer-events: none;
}

.known__subject {
  grid-area: subject;
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

.known__facts {
  grid-area: facts;
  display: flex;
  flex-wrap: wrap;
  gap: 0.125rem 1rem;
}

.known__open {
  grid-area: open;
  opacity: 0.6;
}

.known__more {
  display: flex;
  justify-content: center;
  margin-top: 0.5rem;
}
</style>
