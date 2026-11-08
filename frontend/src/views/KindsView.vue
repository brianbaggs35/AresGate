<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'

import { errorMessage } from '@/api/client'
import { LANES, type Lane } from '@/api/incidents'
import { fetchFamilies, JUDGED, type Family, type Judged } from '@/api/threats'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import FamilyCard from '@/components/FamilyCard.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import { formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { JUDGED_FILTERS, LANE } from '@/threats'

/**
 * Kinds of incident: every way programs say the same thing about the same sort of place, with
 * those that have threats first, and what you and the AI make of each. What the AI sets aside is
 * set aside by kind, so this is where to check what it was and to overrule it.
 */
const PAGE = 20
const PAUSE = 300

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

interface Asked {
  lane: Lane | null
  judged: Judged | null
  q: string
}

/** What the list is narrowed to is in the address of the page. Anything in it that isn't one of
 * the choices is ignored. */
function askedOf(query: LocationQuery): Asked {
  const one = (name: string) => (typeof query[name] === 'string' ? query[name] : '')
  return {
    lane: LANES.find((name) => name === one('lane')) ?? null,
    judged: JUDGED.find((name) => name === one('judged')) ?? null,
    q: one('q'),
  }
}

const asked = computed(() => askedOf(route.query))
const text = ref(asked.value.q)
const items = ref<Family[]>([])
const total = ref(0)
const loaded = ref(false)
const loadError = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const moreError = ref<string | null>(null)
let latest = 0
let timer: ReturnType<typeof setTimeout> | undefined

const LANE_CHOICES = [
  { value: null, label: 'Any lane' },
  ...LANES.map((value) => ({ value, label: `With ${LANE[value].plural.toLowerCase()}` })),
]

function show(next: Partial<Asked>) {
  const merged = { ...asked.value, ...next }
  const query: Record<string, string> = {}
  if (merged.lane) query.lane = merged.lane
  if (merged.judged) query.judged = merged.judged
  if (merged.q) query.q = merged.q
  void router.replace({ query })
}

function type(value: string) {
  text.value = value
  clearTimeout(timer)
  timer = setTimeout(() => {
    show({ q: value.trim() })
  }, PAUSE)
}

function queryOf(offset: number) {
  const { lane, judged, q } = asked.value
  return {
    ...(lane ? { lane } : {}),
    ...(judged ? { judged } : {}),
    ...(q ? { q } : {}),
    limit: PAGE,
    offset,
  }
}

async function load() {
  const mine = ++latest
  loading.value = true
  try {
    const page = await session.call(() => fetchFamilies(queryOf(0)))
    if (mine !== latest) return
    items.value = page.items
    total.value = page.total
    loaded.value = true
    loadError.value = null
    moreError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function more() {
  loadingMore.value = true
  moreError.value = null
  try {
    const page = await session.call(() => fetchFamilies(queryOf(items.value.length)))
    items.value = [...items.value, ...page.items]
    total.value = page.total
  } catch (error) {
    moreError.value = errorMessage(error)
  } finally {
    loadingMore.value = false
  }
}

watch(asked, load)
onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(timer)
})
</script>

<template>
  <AppPage width="wide" class="kinds">
    <PageHeader
      title="Kinds of incident"
      description="Incidents that programs reported in the same words about the same sort of place. An AI judges a kind once, and that answer covers all of it."
      :back="{ to: { name: 'threats' }, label: 'Threats' }"
    />

    <div class="kinds__filters">
      <v-text-field
        label="Search the kinds"
        :model-value="text"
        :prepend-inner-icon="Search"
        clearable
        hide-details
        data-test="kinds-search"
        @update:model-value="type($event ?? '')"
      />
      <v-select
        label="Lane"
        :items="LANE_CHOICES"
        item-title="label"
        item-value="value"
        :model-value="asked.lane"
        hide-details
        data-test="kinds-lane"
        @update:model-value="show({ lane: $event })"
      />
      <v-select
        label="Judged by"
        :items="JUDGED_FILTERS"
        item-title="label"
        item-value="value"
        :model-value="asked.judged"
        hide-details
        data-test="kinds-judged"
        @update:model-value="show({ judged: $event })"
      />
    </div>

    <LoadError
      v-if="loadError && !loaded"
      :message="loadError"
      :loading="loading"
      data-test="kinds-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!loaded" type="card, card" data-test="kinds-loading" />
    <template v-else>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="kinds-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>
      <p class="text-body-medium text-medium-emphasis" data-test="kinds-total">
        {{ formatCount(total) }} {{ total === 1 ? 'kind' : 'kinds' }}
      </p>
      <ul v-if="items.length" class="kinds__list" data-test="kinds-list">
        <li v-for="family in items" :key="family.id">
          <FamilyCard :family="family" />
        </li>
      </ul>
      <EmptyState
        v-else
        title="No kinds match"
        description="Nothing is going on that matches, or nothing is going on."
        data-test="kinds-empty"
      />
      <div v-if="items.length < total" class="kinds__more">
        <v-alert v-if="moreError" type="error" variant="tonal" data-test="kinds-more-error">
          {{ moreError }}
        </v-alert>
        <v-btn variant="tonal" :loading="loadingMore" data-test="kinds-more" @click="more">
          Show more ({{ formatCount(total - items.length) }} left)
        </v-btn>
      </div>
    </template>
  </AppPage>
</template>

<style scoped>
.kinds__filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
}

@media (min-width: 720px) {
  .kinds__filters {
    grid-template-columns: minmax(0, 2fr) repeat(2, minmax(0, 1fr));
  }
}

.kinds__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.kinds__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}
</style>
