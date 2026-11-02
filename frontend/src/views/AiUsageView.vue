<script setup lang="ts">
import { Download, RefreshCw, Sparkles } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import {
  fetchUsage,
  usageCsvUrl,
  type Usage,
  type UsageLimit,
  type UsageRange,
} from '@/api/aiUsage'
import { errorMessage } from '@/api/client'
import {
  cachedShare,
  costWords,
  dailySeries,
  dayLabel,
  formatMetric,
  formatMoney,
  formatTokens,
  groupSeries,
  METRICS,
  purposeLabel,
  RANGES,
  tokensOf,
  type Metric,
} from '@/aiUsage'
import BarChart from '@/charts/BarChart.vue'
import AiLevelCard from '@/components/AiLevelCard.vue'
import AiLimitsCard from '@/components/AiLimitsCard.vue'
import AiCallsTable from '@/components/AiCallsTable.vue'
import AppPage from '@/components/AppPage.vue'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import StatTile from '@/components/StatTile.vue'
import { changeOf } from '@/dashboard'
import { formatCount, formatFigure } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * AI usage, a place in the menu of its own: what AI has been asked to do, how many tokens that
 * took and what it cost, by day, provider, model and use; what took the most; how the month is
 * going; the spending limits; how much AI is used without being asked; and every request, to see
 * exactly what a provider was sent. Costs are estimates. Which AI to use is chosen in Settings > AI.
 */
const session = useSessionStore()

type Grouping = 'provider' | 'model' | 'use'
const GROUPINGS: readonly { key: Grouping; label: string }[] = [
  { key: 'provider', label: 'Provider' },
  { key: 'model', label: 'Model' },
  { key: 'use', label: 'Use' },
]

const range = ref<UsageRange>('30d')
const metric = ref<Metric>('cost')
const grouping = ref<Grouping>('model')
const usage = ref<Usage | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
/** Counts up when the numbers are asked for again, so the list of requests asks again too. */
const refreshed = ref(0)
/** Which load is the newest, so the answer to an older one (for another range) is dropped. */
let latest = 0

async function load() {
  const mine = ++latest
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(() => fetchUsage(range.value))
    if (mine !== latest) return
    usage.value = found
    refreshed.value += 1
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

function pick(next: UsageRange) {
  range.value = next
  void load()
}

function levelChanged(level: Usage['level']) {
  const known = usage.value as Usage
  usage.value = { ...known, level }
}

function limitsChanged(limits: UsageLimit[]) {
  const known = usage.value as Usage
  usage.value = { ...known, limits }
}

const words = computed(
  () => RANGES.find(({ key }) => key === range.value) as (typeof RANGES)[number],
)
const shown = computed(() => usage.value as Usage)

const monthTile = computed(() => {
  const { month } = shown.value
  return month.projected_micros === null
    ? 'Too early in the month to say where it is heading'
    : `On course for about ${formatMoney(month.projected_micros)} by the end of the month`
})
const costTile = computed(() => {
  const { totals, previous } = shown.value
  return changeOf(totals.cost_micros, previous.cost_micros, words.value.before, false)
})
const tokenTile = computed(() => {
  const { totals, previous } = shown.value
  return changeOf(tokensOf(totals), tokensOf(previous), words.value.before, false)
})

const categories = computed(() => shown.value.days.map(dayLabel))
const daily = computed(() => dailySeries(shown.value, metric.value))
const groups = computed(() => {
  const { by_provider: providers, by_model: models, by_purpose: uses } = shown.value
  if (grouping.value === 'provider') return providers
  if (grouping.value === 'model') return models
  return uses.map((group) => ({ ...group, label: purposeLabel(group.key) }))
})
const groupBars = computed(() => groupSeries(groups.value, metric.value))
const metricName = computed(
  () => (METRICS.find(({ key }) => key === metric.value) as (typeof METRICS)[number]).label,
)

onMounted(load)
</script>

<template>
  <AppPage width="wide" class="ai-usage">
    <PageHeader
      title="AI usage"
      description="What AI has been asked to do, how much that took and what it cost. The costs are estimates."
    >
      <template v-if="usage" #actions>
        <ChoiceToggle
          :model-value="range"
          :options="RANGES"
          label="Time range"
          name="range"
          @update:model-value="pick"
        />
        <v-btn
          variant="text"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="refresh"
          @click="load"
        >
          Refresh
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError && !usage"
      :message="loadError"
      :loading="loading"
      data-test="usage-error"
      @retry="load"
    />
    <template v-else-if="usage">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="usage-stale">
        {{ loadError }} What is shown is from before.
      </v-alert>

      <v-card v-if="!usage.ever" class="pa-5 pa-sm-6" data-test="usage-card">
        <EmptyState
          title="AI hasn't been asked anything yet"
          description="Once an AI provider is set up and turned on, every request it is asked shows up here, with the tokens it took and what it cost."
          :icon="Sparkles"
          data-test="usage-never"
        >
          <v-btn
            color="primary"
            variant="tonal"
            :to="{ name: 'settings-ai' }"
            data-test="usage-setup"
          >
            Set up an AI provider
          </v-btn>
        </EmptyState>
      </v-card>
      <div v-else class="tiles" data-test="usage-card">
        <StatTile
          label="This month"
          :value="formatMoney(usage.month.spent_micros)"
          :hint="monthTile"
          data-test="tile-month"
        />
        <StatTile
          label="Cost"
          :value="formatMoney(usage.totals.cost_micros)"
          :hint="`In ${words.long}`"
          :delta="costTile"
          data-test="tile-cost"
        />
        <StatTile
          label="Tokens"
          :value="formatTokens(tokensOf(usage.totals))"
          :hint="`${cachedShare(usage.totals)}% of what was sent was already cached`"
          :delta="tokenTile"
          data-test="tile-tokens"
        />
        <StatTile
          label="Requests"
          :value="formatFigure(usage.totals.calls)"
          :hint="
            usage.totals.failed === 0 ? 'None failed' : `${formatCount(usage.totals.failed)} failed`
          "
          :tone="usage.totals.failed === 0 ? 'good' : 'warning'"
          data-test="tile-requests"
        />
      </div>

      <AiLevelCard :level="usage.level" :levels="usage.levels" @changed="levelChanged" />

      <template v-if="usage.ever">
        <v-alert type="info" variant="tonal" density="compact" data-test="usage-estimate">
          Costs are estimates, worked out from the prices on each provider's own pricing page as
          they were on {{ usage.prices.as_of }}:
          <template v-for="(source, index) in usage.prices.sources" :key="source.url">
            <a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.provider }}</a
            ><template v-if="index < usage.prices.sources.length - 1">, </template>
          </template>
          . Prices change, so what you are billed can differ.
          <template v-if="usage.totals.unpriced > 0">
            {{ formatCount(usage.totals.unpriced) }}
            {{ usage.totals.unpriced === 1 ? 'request used' : 'requests used' }} a model with no
            known price: they are in the tokens, not in the cost.
          </template>
        </v-alert>

        <AiLimitsCard :limits="usage.limits" @changed="limitsChanged" />

        <SectionCard
          title="Usage by day"
          :description="`What each kind of use took on each day of ${words.long}.`"
          data-test="daily-card"
        >
          <template #actions>
            <ChoiceToggle v-model="metric" :options="METRICS" label="What to show" name="metric" />
          </template>
          <BarChart
            :title="`${metricName} by day`"
            :caption="`${metricName} on each day of ${words.long}, by what the AI was used for.`"
            category-label="Day"
            orientation="vertical"
            stacked
            :whole="metric !== 'cost'"
            :categories="categories"
            :series="daily"
            :format="formatMetric(metric)"
            :loading="loading"
            empty-title="Nothing in this time"
            :empty-description="`No requests were made in ${words.long}.`"
            data-test="daily-chart"
          />
        </SectionCard>

        <SectionCard
          title="Where it goes"
          :description="`${metricName} in ${words.long}, by provider, model or use.`"
          data-test="groups-card"
        >
          <template #actions>
            <ChoiceToggle
              v-model="grouping"
              :options="GROUPINGS"
              label="Group by"
              name="grouping"
            />
          </template>
          <BarChart
            :title="`${metricName} by ${grouping}`"
            category-label="Name"
            :whole="metric !== 'cost'"
            :categories="groups.map(({ label }) => label)"
            :series="groupBars"
            :format="formatMetric(metric)"
            :loading="loading"
            empty-title="Nothing in this time"
            :empty-description="`No requests were made in ${words.long}.`"
            data-test="groups-chart"
          />
          <ul
            v-if="groups.some(({ unpriced }) => unpriced > 0)"
            class="mt-3 text-body-medium text-medium-emphasis"
            data-test="groups-unpriced"
          >
            <li v-for="group in groups.filter(({ unpriced }) => unpriced > 0)" :key="group.key">
              {{ group.label }}: {{ costWords(group.cost_micros, group.unpriced) }}
            </li>
          </ul>
        </SectionCard>

        <SectionCard
          title="What took the most"
          :description="`What the AI was asked about that took the most in ${words.long}.`"
          data-test="top-card"
        >
          <EmptyState
            v-if="usage.top.length === 0"
            title="Nothing in particular"
            description="Requests that are about something, such as an incident, are listed here."
            data-test="top-empty"
          />
          <ol v-else class="top">
            <li
              v-for="consumer in usage.top"
              :key="`${consumer.purpose}-${consumer.about}`"
              class="top__item"
              data-test="top-item"
            >
              <div class="top__main">
                <router-link
                  v-if="consumer.incident_id !== null"
                  :to="{ name: 'incident', params: { id: consumer.incident_id } }"
                  class="text-label-large"
                  data-test="top-link"
                >
                  {{ purposeLabel(consumer.purpose) }}: {{ consumer.about }}
                </router-link>
                <span v-else class="text-label-large">
                  {{ purposeLabel(consumer.purpose) }}: {{ consumer.about }}
                </span>
                <span class="text-body-medium text-medium-emphasis">
                  {{ formatCount(consumer.calls) }}
                  {{ consumer.calls === 1 ? 'request' : 'requests' }} ·
                  {{ formatTokens(consumer.tokens) }} tokens
                </span>
              </div>
              <span class="text-body-large tabular-nums">{{
                formatMoney(consumer.cost_micros)
              }}</span>
            </li>
          </ol>
        </SectionCard>

        <AiCallsTable :range="range" :refreshed="refreshed" />

        <div class="download">
          <v-btn
            variant="tonal"
            :prepend-icon="Download"
            :href="usageCsvUrl(range)"
            download
            data-test="download"
          >
            Download {{ words.long }} as a spreadsheet
          </v-btn>
          <span class="text-body-medium text-medium-emphasis">
            A CSV file of every request: when, what for, the model, the tokens and the estimated
            cost. It holds nothing that was sent or said.
          </span>
        </div>
      </template>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="usage-loading" />
  </AppPage>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 1rem;
}

.top {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.top__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant), 0.6);
}

.top__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.download {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}
</style>
