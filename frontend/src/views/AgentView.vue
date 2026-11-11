<script setup lang="ts">
import { CalendarClock, Clock, Gauge, Pencil, Play, ShieldAlert, Square } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  cancelRun,
  fetchAgent,
  fetchRun,
  startRun,
  type AgentDetail,
  type RunDetail,
} from '@/api/agents'
import { errorMessage } from '@/api/client'
import {
  AGENT_STATE,
  RUN_STATUS,
  elapsedMs,
  isLive,
  outcome,
  scheduleText,
  severityOf,
  usageLine,
} from '@/agents'
import AgentChanges from '@/components/AgentChanges.vue'
import AgentDialog from '@/components/AgentDialog.vue'
import AgentFindings from '@/components/AgentFindings.vue'
import AgentGraph from '@/components/AgentGraph.vue'
import AgentTimeline from '@/components/AgentTimeline.vue'
import AgentTrend from '@/components/AgentTrend.vue'
import AgentProposals from '@/components/AgentProposals.vue'
import AgentSetup from '@/components/AgentSetup.vue'
import AgentUsage from '@/components/AgentUsage.vue'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatTile from '@/components/StatTile.vue'
import UndoNotice from '@/components/UndoNotice.vue'
import { formatAgo, formatDue, formatElapsed } from '@/format'
import { usePolling } from '@/polling'
import { SEVERITY } from '@/severity'
import { useSessionStore } from '@/stores/session'

/**
 * One agent: whether it is going, the graph it runs drawn as it runs, what it did step by step,
 * what it found, and its runs so far to look back at. While a run is waiting or going the page
 * follows it, so the owner watches the agent work; looking at an older run stops that until they
 * go back to the newest.
 */
const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const REFRESH_MS = 2000

const agent = ref<AgentDetail | null>(null)
const run = ref<RunDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const problem = ref<string | null>(null)
const busy = ref(false)
const editing = ref(false)
/** The run on screen, and whether it is the newest, which the page moves along as new ones start. */
const chosen = ref<number | null>(null)
const following = ref(true)
const now = ref(Date.now())
const notice = ref<{ show: (done: { text: string; undo: null }) => void } | null>(null)

const id = computed(() => Number(route.params.id))
const state = computed(() => (agent.value ? AGENT_STATE[agent.value.state] : null))
const live = computed(() => isLive(run.value) || agent.value?.state === 'running')
const status = computed(() => (run.value ? RUN_STATUS[run.value.status] : null))
const blocked = computed(() => !!agent.value?.active && !agent.value.allow_active)
const lastRun = computed(() => agent.value?.runs[0] ?? null)
const worstTone = computed(() => {
  const last = lastRun.value
  if (!last?.worst || !last.findings) return 'good'
  return SEVERITY[severityOf(last.worst)].color === 'error' ? 'bad' : 'warning'
})
const finished = computed(() =>
  (agent.value?.runs ?? []).filter(
    (each) => each.status === 'succeeded' || each.status === 'failed',
  ),
)
const succeeded = computed(
  () => finished.value.filter((each) => each.status === 'succeeded').length,
)
/** Whether this agent writes the daily briefing, so that its summary is read as one. */
const briefs = computed(() => agent.value?.template === 'daily_briefing')
const took = computed(() => (run.value ? formatElapsed(elapsedMs(run.value, now.value)) : ''))

async function loadRun(quiet: boolean) {
  const shown = chosen.value
  if (shown === null) {
    run.value = null
    return
  }
  try {
    const next = await session.call(() => fetchRun(id.value, shown))
    if (chosen.value === shown) run.value = next
  } catch (runError) {
    if (!quiet) problem.value = errorMessage(runError)
  }
}

async function load(quiet = false) {
  if (!quiet) loading.value = true
  now.value = Date.now()
  try {
    const next = await session.call(() => fetchAgent(id.value))
    agent.value = next
    error.value = null
    const newest = next.runs[0]?.id ?? null
    if (chosen.value === null || (following.value && chosen.value !== newest)) chosen.value = newest
    await loadRun(quiet)
  } catch (loadError) {
    if (!quiet || agent.value === null) error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

async function choose(runId: number) {
  chosen.value = runId
  following.value = runId === lastRun.value?.id
  await loadRun(false)
}

async function act(request: (token: string) => Promise<unknown>) {
  busy.value = true
  problem.value = null
  try {
    await session.change(request)
    following.value = true
    await load(true)
  } catch (actError) {
    problem.value = errorMessage(actError)
  } finally {
    busy.value = false
  }
}

const start = () => act((token) => startRun(id.value, token))
const stop = () => act((token) => cancelRun(id.value, run.value?.id ?? 0, token))

async function saved(text: string) {
  await load(true)
  notice.value?.show({ text, undo: null })
}

function removed() {
  return router.push({ name: 'agents' })
}

usePolling(() => load(true), REFRESH_MS)
onMounted(() => load())
</script>

<template>
  <AppPage width="wide">
    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="agent-retry"
      data-test="agent-error"
      @retry="load()"
    />

    <template v-else-if="agent && state">
      <PageHeader
        :title="agent.name"
        :description="agent.template_info.tagline"
        :back="{ to: { name: 'agents' }, label: 'Agents' }"
      >
        <template #badge>
          <v-chip
            :color="state.color"
            :prepend-icon="state.icon"
            size="small"
            variant="tonal"
            data-test="agent-state"
          >
            {{ state.label }}
          </v-chip>
        </template>
        <template #actions>
          <v-btn
            v-if="live && run && isLive(run)"
            color="error"
            variant="tonal"
            :prepend-icon="Square"
            :loading="busy"
            data-test="agent-stop"
            @click="stop"
          >
            Stop
          </v-btn>
          <v-btn
            v-else
            color="primary"
            variant="flat"
            :prepend-icon="Play"
            :disabled="live || blocked"
            :loading="busy"
            data-test="agent-start"
            @click="start"
          >
            Run now
          </v-btn>
          <v-btn
            variant="tonal"
            :prepend-icon="Pencil"
            data-test="agent-edit"
            @click="editing = true"
          >
            Edit
          </v-btn>
        </template>
      </PageHeader>

      <v-alert
        v-if="problem"
        type="error"
        variant="tonal"
        density="compact"
        data-test="agent-problem"
      >
        {{ problem }}
      </v-alert>
      <v-alert
        v-if="blocked"
        type="warning"
        variant="tonal"
        density="compact"
        data-test="agent-blocked"
      >
        This agent tests your network, so it is not allowed to yet. Edit it and allow it when you
        want it to run.
      </v-alert>

      <div class="tiles">
        <StatTile
          label="Last run"
          :icon="lastRun ? RUN_STATUS[lastRun.status].icon : Clock"
          :value="lastRun ? RUN_STATUS[lastRun.status].label : 'Never'"
          :hint="
            lastRun
              ? formatAgo(lastRun.finished_at ?? lastRun.started_at ?? lastRun.requested_at)
              : 'Run it to see what it finds'
          "
          :tone="lastRun?.status === 'failed' ? 'bad' : 'neutral'"
          data-test="agent-tile-last"
        />
        <StatTile
          label="Next run"
          :icon="CalendarClock"
          :value="
            agent.next_run_at && agent.enabled ? formatDue(agent.next_run_at) : 'Not scheduled'
          "
          :hint="scheduleText(agent.interval_minutes)"
          data-test="agent-tile-next"
        />
        <StatTile
          label="Findings"
          :icon="ShieldAlert"
          :value="lastRun ? lastRun.findings : '–'"
          hint="In its last run"
          :tone="lastRun ? worstTone : 'neutral'"
          data-test="agent-tile-findings"
        />
        <StatTile
          label="Reliability"
          :icon="Gauge"
          :value="finished.length ? `${succeeded} of ${finished.length}` : '–'"
          hint="Of its recent runs finished"
          data-test="agent-tile-reliable"
        />
      </div>

      <v-card v-if="run" class="pa-5 pa-sm-6 run" data-test="agent-run">
        <header class="run__head">
          <div>
            <h2 class="text-title-large run__title">Run {{ run.id }}</h2>
            <p class="text-body-medium text-medium-emphasis run__meta" data-test="run-meta">
              {{ run.trigger === 'schedule' ? 'By its schedule' : 'Started by you' }} ·
              {{ formatAgo(run.started_at ?? run.requested_at) }}
              <template v-if="run.started_at"> · {{ took }}</template>
            </p>
            <p
              v-if="!isLive(run)"
              class="text-body-medium text-medium-emphasis run__meta"
              data-test="run-usage"
            >
              {{ usageLine(run.usage) }}
              <template v-if="run.model"> · {{ run.model }}</template>
            </p>
          </div>
          <v-chip
            v-if="status"
            :color="status.color"
            :prepend-icon="status.icon"
            variant="tonal"
            data-test="run-status"
          >
            {{ status.label }}
          </v-chip>
        </header>

        <AgentGraph :edges="agent.graph" :run="run" :steps="run.steps" />

        <v-alert
          v-if="run.error"
          type="error"
          variant="tonal"
          density="compact"
          data-test="run-error"
        >
          {{ run.error }}
        </v-alert>
        <p v-if="briefs && run.summary" class="text-label-large" data-test="run-briefing">
          Today's briefing
        </p>
        <p v-if="run.summary" class="text-body-large run__summary" data-test="run-summary">
          {{ run.summary }}
        </p>
        <AgentChanges v-if="run.changes" :changes="run.changes" :findings="run.findings_list" />
        <v-alert v-if="run.ai" type="info" variant="tonal" density="compact" data-test="run-ai">
          The AI took no part in this run: {{ run.ai }}
        </v-alert>
      </v-card>

      <section
        v-if="run && run.findings_list.length"
        class="section"
        aria-labelledby="findings-title"
      >
        <h2 id="findings-title" class="text-title-large">What it found</h2>
        <AgentFindings :findings="run.findings_list" />
      </section>
      <section
        v-else-if="run && run.status === 'succeeded'"
        class="section"
        aria-labelledby="findings-title"
      >
        <h2 id="findings-title" class="text-title-large">What it found</h2>
        <p class="text-body-large text-medium-emphasis" data-test="run-nothing">
          Nothing needed your attention.
        </p>
      </section>

      <section v-if="run" class="section" aria-labelledby="steps-title">
        <h2 id="steps-title" class="text-title-large">What it did</h2>
        <AgentTimeline :steps="run.steps" :live="isLive(run)" />
      </section>

      <EmptyState
        v-if="!run"
        title="It has not run yet"
        description="Press Run now and watch it work, or wait for its schedule."
        data-test="agent-no-runs"
      />

      <section v-if="agent.runs.length" class="section" aria-labelledby="trend-title">
        <h2 id="trend-title" class="text-title-large">How it has been going</h2>
        <v-card class="pa-4 pa-sm-5">
          <AgentTrend :runs="agent.runs" />
        </v-card>
      </section>

      <section v-if="agent.runs.length" class="section" aria-labelledby="history-title">
        <h2 id="history-title" class="text-title-large">Earlier runs</h2>
        <ul class="history" data-test="agent-history">
          <li v-for="each in agent.runs" :key="each.id">
            <button
              type="button"
              class="past"
              :class="{ 'past--on': each.id === run?.id }"
              :aria-pressed="each.id === run?.id"
              data-test="history-run"
              @click="choose(each.id)"
            >
              <v-icon
                :icon="RUN_STATUS[each.status].icon"
                :color="RUN_STATUS[each.status].color"
                size="20"
                :aria-label="RUN_STATUS[each.status].label"
                role="img"
                :aria-hidden="false"
              />
              <span class="past__text">
                <span class="text-body-large">Run {{ each.id }} · {{ outcome(each) }}</span>
                <span class="text-body-small text-medium-emphasis">
                  {{ each.trigger === 'schedule' ? 'By its schedule' : 'Started by you' }} ·
                  {{ formatAgo(each.finished_at ?? each.requested_at) }}
                </span>
              </span>
            </button>
          </li>
        </ul>
      </section>

      <section
        v-if="agent.template_info.proposes"
        class="section"
        aria-labelledby="suggestions-title"
        data-test="agent-suggestions"
      >
        <h2 id="suggestions-title" class="text-title-large">What it suggests tidying</h2>
        <AgentProposals :suggestions="agent.suggestions" @changed="saved" />
      </section>

      <section class="section" aria-labelledby="usage-title">
        <h2 id="usage-title" class="text-title-large">What it costs</h2>
        <AgentUsage :usage="agent.usage" :days="agent.days" />
      </section>

      <section class="section" aria-labelledby="about-title">
        <h2 id="about-title" class="text-title-large">How it is set up</h2>
        <v-card class="pa-5 setup">
          <dl class="setup__facts">
            <div>
              <dt class="text-label-large">Kind</dt>
              <dd class="text-body-large" data-test="setup-kind">{{ agent.template_name }}</dd>
            </div>
            <div>
              <dt class="text-label-large">Schedule</dt>
              <dd class="text-body-large" data-test="setup-schedule">
                {{
                  agent.interval_minutes !== null && !agent.enabled
                    ? `Paused (${scheduleText(agent.interval_minutes).toLowerCase()})`
                    : scheduleText(agent.interval_minutes)
                }}
              </dd>
            </div>
            <div v-if="agent.active">
              <dt class="text-label-large">Tests the network</dt>
              <dd class="text-body-large" data-test="setup-allow">
                {{ agent.allow_active ? 'Allowed' : 'Not allowed yet' }}
              </dd>
            </div>
            <div>
              <dt class="text-label-large">Your instructions</dt>
              <dd class="text-body-large setup__goal" data-test="setup-goal">
                {{ agent.goal || 'None. It does what its kind does.' }}
              </dd>
            </div>
          </dl>
          <v-divider class="my-4" />
          <AgentSetup :template="agent.template_info" />
        </v-card>
      </section>

      <AgentDialog
        v-model="editing"
        :agent="agent"
        :templates="[agent.template_info]"
        @saved="saved"
        @removed="removed"
      />
    </template>

    <v-skeleton-loader v-else type="heading, card, card" data-test="agent-loading" />

    <UndoNotice ref="notice" />
  </AppPage>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.75rem;
}

.run {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.run__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.run__title,
.run__meta,
.run__summary {
  margin: 0;
}

.run__summary {
  overflow-wrap: anywhere;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section h2,
.section p {
  margin: 0;
}

.history {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.past {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid transparent;
  border-radius: 0.875rem;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.2s;
}

.past:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.past:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.past--on {
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.08);
}

.past__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}

.setup__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem 1.5rem;
  margin: 0;
}

.setup__facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.setup__facts dd {
  margin: 0.125rem 0 0;
}

.setup__goal {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
