<script setup lang="ts">
import { ArrowRight, RefreshCw, SlidersHorizontal } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { WINDOWS, type DashboardWindow } from '@/api/dashboard'
import { fetchIncidents, LANES, type Incident, type Lane } from '@/api/incidents'
import { fetchOverview, type Overview } from '@/api/threats'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import FamilyCard from '@/components/FamilyCard.vue'
import IncidentCard from '@/components/IncidentCard.vue'
import JudgedNotice from '@/components/JudgedNotice.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatFunnel from '@/components/ThreatFunnel.vue'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'
import { coverageSentence, firstLane, LANE } from '@/threats'
import type { Judged } from '@/verdicts'

/**
 * Threats: what is a real attack and what is background, in the window. The funnel at the top
 * says how seventy thousand reports came down to a few incidents; under it, the threats and the
 * suspects are cards that can be judged where they are, and the background is the kinds of
 * incident that were set aside, each of which can be opened, checked and overruled. Nothing is
 * thrown away: every report is in the Logs and every incident in Incidents.
 */
const REFRESH_SECONDS = 30
const PAGE = 20

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const range = ref<DashboardWindow>('24h')
const overview = ref<Overview | null>(null)
const items = ref<Incident[]>([])
const total = ref(0)
const loadError = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const moreError = ref<string | null>(null)
let latest = 0

/** The lane on screen: the one in the address of the page, else the first with something in it. */
const lane = computed<Lane>(() => {
  const asked = LANES.find((name) => name === route.query.lane)
  return asked ?? firstLane((overview.value as Overview).funnel)
})
const listed = computed(() => lane.value !== 'background')
const windowInfo = computed(
  () => WINDOWS.find(({ key }) => key === range.value) as (typeof WINDOWS)[number],
)
const lastWords = computed(() => `the last ${windowInfo.value.label}`)
// Both of these are read only once there is an overview to show.
const counts = computed(() => {
  const found = (overview.value as Overview).funnel
  return { threat: found.threats, suspect: found.suspects, background: found.background }
})

/** Fetches the overview, and the incidents of the lane, which are what its count counted. */
async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchOverview(range.value))
    const shown = LANES.find((name) => name === route.query.lane) ?? firstLane(found.funnel)
    const page =
      shown === 'background'
        ? null
        : await session.call(() =>
            fetchIncidents({
              lanes: [shown],
              q: `since:${found.window.start}`,
              order: 'priority',
              limit: PAGE,
            }),
          )
    if (mine !== latest) return
    overview.value = found
    if (page) {
      items.value = page.items
      total.value = page.total
    } else {
      items.value = []
      total.value = 0
    }
    loadError.value = null
    moreError.value = null
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function more() {
  const info = overview.value as Overview
  loadingMore.value = true
  moreError.value = null
  try {
    const page = await session.call(() =>
      fetchIncidents({
        lanes: [lane.value],
        q: `since:${info.window.start}`,
        order: 'priority',
        limit: PAGE,
        offset: items.value.length,
      }),
    )
    items.value = [...items.value, ...page.items]
    total.value = page.total
  } catch (error) {
    moreError.value = errorMessage(error)
  } finally {
    loadingMore.value = false
  }
}

function pickLane(next: Lane) {
  void router.replace({ query: { lane: next } })
}

function pickRange(next: DashboardWindow) {
  range.value = next
}

const notice = ref<{ show: (verdict: Judged) => void } | null>(null)

/** A card gave a verdict: say so, and ask again, since it can leave the lane. */
function judged(verdict: Judged) {
  notice.value?.show(verdict)
  void load(true)
}

watch([range, () => route.query.lane], () => load())
onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="threats">
    <PageHeader
      title="Threats"
      description="Real attacks, separated from the noise. Everything else is kept, grouped and one click away."
    >
      <template #actions>
        <v-btn-toggle
          :model-value="range"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Time range"
          data-test="range"
          @update:model-value="pickRange"
        >
          <v-btn
            v-for="option in WINDOWS"
            :key="option.key"
            :value="option.key"
            :data-test="`range-${option.key}`"
          >
            {{ option.label }}
          </v-btn>
        </v-btn-toggle>
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
      v-if="loadError && !overview"
      :message="loadError"
      :loading="loading"
      data-test="threats-error"
      @retry="load()"
    />
    <v-skeleton-loader v-else-if="!overview" type="card, card" data-test="threats-loading" />
    <template v-else>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="threats-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>

      <SectionCard
        title="From reports to threats"
        description="Every report is counted, each alert once, and alerts about the same thing are one incident."
        data-test="funnel-card"
      >
        <ThreatFunnel :funnel="overview.funnel" :window="lastWords" />
        <div class="threats__coverage">
          <p class="text-body-medium" data-test="coverage">
            {{ coverageSentence(overview.coverage, overview.watching) }}
          </p>
          <div class="threats__links">
            <v-btn
              variant="text"
              :append-icon="ArrowRight"
              :to="{ name: 'kinds' }"
              data-test="kinds-link"
            >
              Kinds of incident
            </v-btn>
            <v-btn
              variant="text"
              :prepend-icon="SlidersHorizontal"
              :to="{ name: 'settings-threat-detection' }"
              data-test="tune-link"
            >
              Tune threat detection
            </v-btn>
          </div>
        </div>
      </SectionCard>

      <v-btn-toggle
        :model-value="lane"
        mandatory
        divided
        density="comfortable"
        variant="outlined"
        color="primary"
        aria-label="Show incidents that are"
        class="threats__lanes"
        data-test="lanes"
        @update:model-value="pickLane"
      >
        <v-btn
          v-for="name in LANES"
          :key="name"
          :value="name"
          :prepend-icon="LANE[name].icon"
          :data-test="`lane-${name}`"
        >
          {{ LANE[name].plural }}
          <span
            class="threats__count text-medium-emphasis tabular-nums"
            :data-test="`count-${name}`"
            >{{ formatCount(counts[name]) }}</span
          >
        </v-btn>
      </v-btn-toggle>
      <p class="text-body-large threats__meaning" data-test="lane-meaning">
        {{ LANE[lane].meaning }}
      </p>

      <JudgedNotice ref="notice" @undone="load(true)" />

      <template v-if="listed">
        <ul v-if="items.length" class="threats__list" data-test="lane-list">
          <li v-for="incident in items" :key="incident.id">
            <IncidentCard :incident="incident" @judged="judged" />
          </li>
        </ul>
        <EmptyState
          v-else
          :title="lane === 'threat' ? 'No threats' : 'No suspects'"
          :description="
            lane === 'threat'
              ? `Nothing in ${lastWords} looks like a real attack.`
              : `Nothing in ${lastWords} is worth a look beyond the threats.`
          "
          data-test="lane-empty"
        />
        <div v-if="items.length < total" class="threats__more">
          <v-alert v-if="moreError" type="error" variant="tonal" data-test="more-error">
            {{ moreError }}
          </v-alert>
          <v-btn variant="tonal" :loading="loadingMore" data-test="more" @click="more">
            Show more ({{ formatCount(total - items.length) }} left)
          </v-btn>
        </div>
      </template>
      <template v-else>
        <ul v-if="overview.families.length" class="threats__list" data-test="kind-list">
          <li v-for="family in overview.families" :key="family.id">
            <FamilyCard :family="family" />
          </li>
        </ul>
        <EmptyState
          v-else
          title="Nothing in the background"
          description="No kind of incident is going on."
          data-test="kind-empty"
        />
        <div class="threats__links">
          <v-btn
            variant="tonal"
            :append-icon="ArrowRight"
            :to="{ name: 'kinds' }"
            data-test="all-kinds"
          >
            See every kind
          </v-btn>
          <v-btn
            variant="text"
            :append-icon="ArrowRight"
            :to="{ name: 'incidents', query: { lane: 'background' } }"
            data-test="background-incidents"
          >
            Open the background in Incidents
          </v-btn>
        </div>
      </template>
    </template>
  </AppPage>
</template>

<style scoped>
.threats__coverage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.threats__coverage p {
  margin: 0;
}

.threats__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
}

.threats__lanes {
  align-self: flex-start;
  max-width: 100%;
  overflow-x: auto;
}

.threats__count {
  margin-inline-start: 0.5rem;
}

.threats__meaning {
  margin: 0;
}

.threats__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.threats__more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}
</style>
