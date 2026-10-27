<script setup lang="ts">
import { CircleCheck, Clock, Gauge, Layers, Laptop, ShieldBan, Waypoints } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import {
  fetchIncident,
  setIncidentStatus,
  type IncidentDetail,
  type IncidentStatus,
} from '@/api/incidents'
import { fetchVerdicts, type Verdict } from '@/api/verdicts'
import BarChart from '@/charts/BarChart.vue'
import AppPage from '@/components/AppPage.vue'
import IncidentAddresses from '@/components/IncidentAddresses.vue'
import IncidentReasons from '@/components/IncidentReasons.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import IncidentTimeline from '@/components/IncidentTimeline.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import StatTile from '@/components/StatTile.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import VerdictPanel from '@/components/VerdictPanel.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import {
  CONFIDENCE,
  STATUS,
  actionsFor,
  changedTo,
  otherAddresses,
  spanOf,
  spreadOf,
} from '@/incidents'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'
import { mutedIn } from '@/verdicts'

/** How often the page asks again while it is on screen. */
const REFRESH_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const id = computed(() => Number(route.params.id))

const incident = ref<IncidentDetail | null>(null)
/** Every verdict there is. The page doesn't depend on them: without them it can't say which
 * apply here, and goes on without. */
const verdicts = ref<Verdict[]>([])
const loadError = ref<string | null>(null)
/** The incident isn't there, which asking again won't change. */
const missing = ref(false)
const loading = ref(false)
const updatedAt = ref<Date | null>(null)
/** The status being changed to, while the change is under way. */
const changing = ref<IncidentStatus | null>(null)
/** What the last change did, or why it didn't. */
const notice = ref<string | null>(null)
const changeError = ref<string | null>(null)
let latest = 0

/** Fetches the incident. A refresh in the background (`quiet`) leaves what is on screen as it is
 * until the answer comes, and keeps it if there is none. */
async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchIncident(id.value))
    // A change under way will answer with a newer one.
    if (mine !== latest || changing.value) return
    incident.value = found
    updatedAt.value = new Date()
    loadError.value = null
    missing.value = false
  } catch (error) {
    if (mine !== latest) return
    loadError.value = errorMessage(error)
    missing.value = error instanceof ApiError && error.status === 404
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function loadVerdicts() {
  try {
    verdicts.value = await session.call(fetchVerdicts)
  } catch {
    // What the incident says of its signals is still there, and so is the means to say more.
  }
}

/** Asks for the incident and the verdicts again, after one was given or taken back. */
async function refresh() {
  await Promise.all([load(true), loadVerdicts()])
}

async function change(status: IncidentStatus) {
  changing.value = status
  notice.value = null
  changeError.value = null
  try {
    incident.value = await session.change((token) => setIncidentStatus(id.value, status, token))
    notice.value = changedTo(status)
    loadError.value = null
  } catch (error) {
    changeError.value = errorMessage(error)
  } finally {
    changing.value = null
  }
}

const shown = computed(() => incident.value as IncidentDetail)
const actions = computed(() => actionsFor(shown.value.status))
const others = computed(() => otherAddresses(shown.value).length)
const programs = computed(() => shown.value.sources.map(({ name }) => name).join(', '))

/** When it began and when it last did something, as a line under the title. */
const when = computed(() => {
  const { first_seen_at: first, last_seen_at: last } = shown.value
  return `First signal ${formatDateTime(first)}, the last ${formatAgo(last)}.`
})
/** What its status means, and when it was set, if anyone has. */
const meaning = computed(() => {
  const { status, status_changed_at: changed } = shown.value
  const set = changed ? ` Set ${formatAgo(changed)}.` : ''
  return `${STATUS[status].label}: ${STATUS[status].meaning}${set}`
})
/** How long its signals came in over, and how many of them your verdicts keep from counting. */
const signalsHint = computed(() => {
  const muted = mutedIn(shown.value)
  return muted > 0
    ? `${spanOf(shown.value)}, ${formatCount(muted)} not counted`
    : spanOf(shown.value)
})

const blocked = computed(() => {
  const count = shown.value.blocked
  if (count === null) {
    return { value: 'None', hint: 'It is about a rule' }
  }
  return {
    value: formatCount(count),
    hint: 'Of its address, around then',
  }
})

const spread = computed(() => spreadOf(shown.value.signals, shown.value.sources))
const listed = computed(() => shown.value.signals.length)
const caption = computed(() => {
  const base = `Signals in each ${spread.value.width}, by the program that reported them.`
  return listed.value < shown.value.signal_count ? `${base} Only those listed below.` : base
})

const updated = computed(() =>
  new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(updatedAt.value as Date),
)

onMounted(() => Promise.all([load(), loadVerdicts()]))
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="incident">
    <template v-if="incident">
      <PageHeader :title="shown.title" :back="{ to: { name: 'incidents' }, label: 'Incidents' }">
        <div class="incident__chips">
          <SeverityChip :severity="shown.severity" />
          <IncidentStatusChip :status="shown.status" />
          <VerdictChip v-if="shown.verdict" :verdict="shown.verdict" />
          <v-chip variant="outlined" :prepend-icon="Gauge" data-test="confidence-chip">
            {{ CONFIDENCE[shown.confidence_level] }} confidence
          </v-chip>
        </div>
        <p class="text-body-medium text-medium-emphasis" data-test="incident-when">{{ when }}</p>
        <p class="text-body-medium text-medium-emphasis" data-test="incident-meaning">
          {{ meaning }}
        </p>
        <template #actions>
          <v-btn
            v-for="action in actions"
            :key="action.status"
            :variant="action.primary ? 'flat' : 'outlined'"
            :color="action.primary ? 'primary' : undefined"
            :prepend-icon="action.icon"
            :loading="changing === action.status"
            :disabled="changing !== null && changing !== action.status"
            :data-test="`action-${action.status}`"
            @click="change(action.status)"
          >
            {{ action.label }}
          </v-btn>
        </template>
      </PageHeader>

      <output v-if="notice" class="incident__notice text-body-large" data-test="notice">
        <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
        {{ notice }}
      </output>
      <v-alert
        v-if="changeError"
        type="error"
        variant="tonal"
        closable
        data-test="change-error"
        @click:close="changeError = null"
      >
        {{ changeError }}
      </v-alert>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="incident-stale">
        {{ loadError }} What is shown is from {{ updated }}.
      </v-alert>

      <div class="incident__tiles" data-test="tiles">
        <StatTile
          label="Signals"
          :value="formatCount(shown.signal_count)"
          :hint="signalsHint"
          :icon="Layers"
          data-test="tile-signals"
        />
        <StatTile
          label="Programs"
          :value="formatCount(shown.sources.length)"
          :hint="programs"
          :icon="Waypoints"
          data-test="tile-programs"
        />
        <StatTile
          label="Addresses"
          :value="formatCount(shown.addresses.length)"
          :hint="
            others > 0
              ? `${formatCount(shown.devices.length)} on your network`
              : 'Only the one it is about'
          "
          :icon="Laptop"
          data-test="tile-addresses"
        />
        <StatTile
          label="Firewall blocks"
          :value="blocked.value"
          :hint="blocked.hint"
          :icon="ShieldBan"
          data-test="tile-blocked"
        />
      </div>

      <div class="incident__top">
        <SectionCard
          title="Why AresGate is this sure"
          description="Each reason adds points, and the points make up the confidence."
          data-test="reasons-card"
        >
          <IncidentReasons
            :reasons="shown.reasons"
            :confidence="shown.confidence"
            :level="shown.confidence_level"
          />
        </SectionCard>

        <SectionCard title="On your network" data-test="addresses-card">
          <IncidentAddresses
            :subject="shown.subject"
            :addresses="shown.addresses"
            :devices="shown.devices"
          />
        </SectionCard>
      </div>

      <VerdictPanel :incident="shown" :verdicts="verdicts" @changed="refresh" />

      <v-card v-if="shown.signals.length > 1" class="pa-5 pa-sm-6" data-test="spread-card">
        <BarChart
          title="Signals over time"
          :caption="caption"
          category-label="Time"
          orientation="vertical"
          stacked
          whole
          :categories="spread.categories"
          :series="spread.series"
          data-test="spread-chart"
        />
      </v-card>

      <SectionCard
        title="Timeline"
        description="Every signal, whichever program saw it, oldest first."
        data-test="timeline-card"
      >
        <template #actions>
          <v-icon :icon="Clock" aria-hidden="true" />
        </template>
        <IncidentTimeline :signals="shown.signals" :total="shown.signal_count" />
      </SectionCard>

      <p class="text-body-medium text-medium-emphasis" data-test="updated">
        Updated {{ updated }}. This page asks again every {{ REFRESH_SECONDS }} seconds while it is
        open.
      </p>
    </template>

    <template v-else-if="loadError">
      <PageHeader title="Incident" :back="{ to: { name: 'incidents' }, label: 'Incidents' }" />
      <LoadError
        :message="missing ? `${loadError} It may have been removed.` : loadError"
        :can-retry="!missing"
        :loading="loading"
        data-test="incident-error"
        @retry="load()"
      />
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="incident-loading" />
  </AppPage>
</template>

<style scoped>
.incident {
  container-type: inline-size;
}

.incident__tiles,
.incident__top {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}

/* Two numbers to a row on a phone, so the four fit without a long scroll. */
.incident__tiles {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.incident__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.incident__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

@container (min-width: 640px) {
  .incident__tiles {
    gap: 1.5rem;
  }
}

@container (min-width: 900px) {
  .incident__tiles {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .incident__top {
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    align-items: start;
  }
}
</style>
