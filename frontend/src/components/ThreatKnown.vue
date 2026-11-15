<script setup lang="ts">
import { ChevronRight, Gavel, Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchKnownThreats,
  searchThreatIntel,
  type Judgement,
  type KnownPage,
  type Lookup,
  type Ruling,
  type SubjectKind,
} from '@/api/threatIntel'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { formatAgo, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { JUDGEMENT, JUDGEMENTS, RULING, tallyOf, typeOf, withRuling } from '@/threatIntel'

/**
 * What AresGate knows of one kind of subject (IP addresses, domains or web addresses): every
 * answer it has kept, from every service, newest first, whether a search or a background lookup
 * asked for it. A subject is one row, with a button for the answer of each service that gave one,
 * so that what the services say of it can be told apart and compared. Looking through them asks no
 * service anything. An answer opens as the report it was, and Check again asks its service for a
 * newer one, which counts toward that service's limits as a search does. Where the owner ruled a
 * subject safe or suspicious, that is what its row says, and the filters and counts follow.
 * `version` changes when something on the page got an answer, so the list is read again.
 */
const props = defineProps<{ kind: SubjectKind; version?: number }>()
const type = computed(() => typeOf(props.kind))
const emit = defineEmits<{ refused: []; ruled: [] }>()

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
      fetchKnownThreats({
        kind: props.kind,
        q: text.value,
        judgement: judgement.value,
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

/** A sentence a screen reader says for the button of one service's answer. */
function describe(item: Lookup): string {
  const ruled = item.ruling
    ? ` You ruled it ${RULING[item.ruling.verdict].short.toLowerCase()}.`
    : ''
  return `${item.subject}, ${item.provider_name}: ${JUDGEMENT[item.judgement].short}, ${tallyOf(item)}.${ruled} Open its report.`
}

interface Subject {
  subject: string
  /** What the services' answers come to, the one that matters most. */
  judgement: Judgement
  ruling: Ruling | null
  answers: Lookup[]
}

/** The answers by subject, in the order the newest of each came. A ruling holds for a subject
 * whichever service answered, so every one of its answers carries it. */
const subjects = computed<Subject[]>(() => {
  const by = new Map<string, Lookup[]>()
  // Only read once the list has been, so there is a page.
  for (const item of (page.value as KnownPage).items) {
    by.set(item.subject, [...(by.get(item.subject) ?? []), item])
  }
  return [...by.entries()].map(([subject, answers]) => ({
    subject,
    answers,
    ruling: answers[0]?.ruling ?? null,
    // Every answer's judgement is one of those listed, so one is found.
    judgement: JUDGEMENTS.find((name) =>
      answers.some((one) => one.judgement === name),
    ) as Judgement,
  }))
})

/** Shows the answer that is open as the owner ruled it, or as the service made it where the ruling
 * was taken back. The page is told, and reads the list again, whose counts and filters follow. */
function ruled(ruling: Ruling | null) {
  // Only the report that is open can say this, so there is one.
  opened.value = withRuling(opened.value as Lookup, ruling)
  emit('ruled')
}

/** Asks the service again about the answer that is open, and shows what came back. */
async function checkAgain() {
  const item = opened.value
  if (!item || checking.value) return
  checking.value = true
  problem.value = null
  try {
    opened.value = await session.change((token) =>
      searchThreatIntel(item.provider, item.subject, token, true, props.kind),
    )
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
    :description="`Every answer the services gave about ${type.plural} is kept here, whether you searched for it or AresGate looked it up for an incident. Looking through them asks no service anything. An answer is checked again once it is no longer fresh: after two days if it was flagged or had no report, and after a week if nothing flagged it. Answers nobody has looked at for the time set under Retention are removed.`"
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
      :description="`The first answer from a search, or from a lookup about an incident, shows up here for ${type.plural}.`"
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

      <fieldset class="known__filters" data-test="known-filters">
        <legend class="known__legend">Judgement</legend>
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
      </fieldset>

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
        <li
          v-for="one in subjects"
          :key="one.subject"
          class="known__subject-row"
          :data-judgement="one.judgement"
          data-test="known-row"
        >
          <div class="known__head">
            <span class="known__subject" data-test="known-subject">{{ one.subject }}</span>
            <v-chip
              v-if="one.ruling"
              :prepend-icon="Gavel"
              variant="outlined"
              size="x-small"
              data-test="known-ruled"
            >
              Ruled by you
            </v-chip>
          </div>
          <ul class="known__answers">
            <li v-for="item in one.answers" :key="item.provider">
              <button
                type="button"
                class="known__answer"
                :aria-label="describe(item)"
                :data-provider="item.provider"
                data-test="known-answer"
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
                <span class="known__service" data-test="known-service">
                  {{ item.provider_name }}
                </span>
                <span class="known__facts text-body-small text-medium-emphasis">
                  <span data-test="known-tally">{{ tallyOf(item) }}</span>
                  <span data-test="known-checked">Checked {{ formatAgo(item.checked_at) }}</span>
                  <span v-if="item.stale" data-test="known-stale">Due to be checked again</span>
                </span>
                <ChevronRight :size="18" aria-hidden="true" class="known__open" />
              </button>
            </li>
          </ul>
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
      @ruled="ruled"
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
  margin: 0.75rem 0 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

/* Read out as the name of the group, and not shown. */
.known__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
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

.known__subject-row {
  padding: 0.75rem 0;
}

.known__subject-row + .known__subject-row {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.known__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  padding: 0 0.5rem;
}

.known__subject {
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

.known__answers {
  margin: 0.25rem 0 0;
  padding: 0;
  list-style: none;
}

.known__answer {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas:
    'judgement service open'
    'facts facts open';
  align-items: center;
  gap: 0.125rem 0.75rem;
  width: 100%;
  padding: 0.5rem;
  border: 0;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.known__answer:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.known__answer:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.known__judgement {
  grid-area: judgement;
  pointer-events: none;
}

.known__service {
  grid-area: service;
  min-width: 0;
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
