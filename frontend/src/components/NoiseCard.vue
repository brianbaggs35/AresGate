<script setup lang="ts">
import { BellMinus, ListFilter } from '@lucide/vue'
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import type { DashboardWindow, Noise, NoisySignature, SourceAlerts } from '@/api/dashboard'
import { giveVerdict } from '@/api/verdicts'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { logsQuery, nameOf, percentOf, scopeOf, shareOf, summaryOf } from '@/noise'
import { SEVERITY } from '@/severity'
import { useSessionStore } from '@/stores/session'
import type { Judged, Scope } from '@/verdicts'

/**
 * Where the alerts come from: which program reported most of them, and the alerts that were
 * reported most often, each with how serious it was, how many addresses it came from and went to,
 * and a way to say it is not worth hearing about. A page that is full of alerts is usually a
 * page with one or two chatty rules on it, and this is where they show. *Quiet this* gives a
 * low priority verdict for that alert from that program (the same verdict the incident cards
 * give), so whoever shows the card says what was done and offers to take it back (`judged`).
 */
const props = defineProps<{
  noise: Noise
  /** How many alerts there were in all in the window, which the shares are of. */
  total: number
  window: DashboardWindow
  /** The window in words that fit "in ...": "the last 24 hours". */
  lastWords: string
}>()
const emit = defineEmits<{ judged: [Judged] }>()

const session = useSessionStore()

/** Which alert a verdict is being given for, and what went wrong with the last. */
const giving = ref<string | null>(null)
const failure = ref<string | null>(null)

const summary = computed(() => summaryOf(props.noise, props.total))

function key(item: NoisySignature): string {
  return `${item.source}\u0000${item.signature ?? ''}`
}

async function quiet(item: NoisySignature) {
  // Only an alert that names a rule has the button, so there is a scope to judge it by.
  const scope = scopeOf(item) as Scope
  giving.value = key(item)
  failure.value = null
  try {
    const note = `Quieted from the dashboard: reported ${formatCount(item.count)} times in ${props.lastWords}.`
    const kept = await session.change((token) =>
      giveVerdict({ verdict: 'low_priority', ...scope.request, note }, token),
    )
    emit('judged', { kind: 'low_priority', scope, rule: kept })
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    giving.value = null
  }
}

/** What a program reported, in a few words: "ntopng: 635, 620 serious". */
function sourceLabel(item: SourceAlerts): string {
  const serious = item.serious > 0 ? `, ${formatCount(item.serious)} serious` : ''
  return `${item.source_name}: ${formatCount(item.total)}${serious}`
}

const reach = (item: NoisySignature) =>
  `From ${formatCount(item.from_addresses)} ${item.from_addresses === 1 ? 'address' : 'addresses'} to ${formatCount(item.to_addresses)}`
</script>

<template>
  <SectionCard
    title="What is making the noise"
    :description="`The alerts that were reported most in ${lastWords}.`"
    class="noise"
    data-test="noise-card"
  >
    <p class="noise__summary text-body-large" data-test="noise-summary">{{ summary }}</p>

    <ul class="noise__sources" aria-label="Alerts by program" data-test="noise-sources">
      <li v-for="item in noise.sources" :key="item.source" data-test="noise-source">
        <v-chip variant="outlined" size="small">{{ sourceLabel(item) }}</v-chip>
      </li>
    </ul>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="comfortable"
      class="mb-3"
      data-test="noise-failure"
    >
      {{ failure }}
    </v-alert>

    <ol class="noise__list" data-test="noise-list">
      <li
        v-for="item in noise.signatures"
        :key="key(item)"
        class="noise__item"
        :style="{ '--noise-accent': `rgb(var(--v-theme-${SEVERITY[item.severity].color}))` }"
        data-test="noise-item"
      >
        <div class="noise__head">
          <span class="noise__name text-body-large" data-test="noise-name">{{ nameOf(item) }}</span>
          <span class="noise__count text-title-medium" data-test="noise-count">
            {{ formatCount(item.count) }}
            <span class="text-body-medium text-medium-emphasis"
              >· {{ percentOf(item.count, total) }}</span
            >
          </span>
        </div>
        <div class="noise__bar" aria-hidden="true">
          <span :style="{ width: `${Math.max(2, shareOf(item.count, total) * 100)}%` }" />
        </div>
        <div class="noise__meta text-body-medium text-medium-emphasis">
          <SeverityChip :severity="item.severity" />
          <span data-test="noise-program">{{ item.source_name }}</span>
          <span data-test="noise-reach">{{ reach(item) }}</span>
          <span>
            <time :datetime="item.first_at" :title="formatDateTime(item.first_at)">{{
              formatAgo(item.first_at)
            }}</time>
            to
            <time :datetime="item.last_at" :title="formatDateTime(item.last_at)">{{
              formatAgo(item.last_at)
            }}</time>
          </span>
        </div>
        <div class="noise__actions">
          <VerdictChip v-if="item.verdict" :verdict="item.verdict" />
          <v-btn
            v-else-if="item.signature !== null"
            variant="tonal"
            size="small"
            :prepend-icon="BellMinus"
            :loading="giving === key(item)"
            :disabled="giving !== null"
            :aria-label="`Quiet this: ${nameOf(item)}`"
            data-test="noise-quiet"
            @click="quiet(item)"
          >
            Quiet this
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="ListFilter"
            :to="{ name: 'logs', query: { q: logsQuery(item, window) } }"
            :aria-label="`See in logs: ${nameOf(item)}`"
            data-test="noise-logs"
          >
            See in logs
          </v-btn>
        </div>
      </li>
    </ol>
  </SectionCard>
</template>

<style scoped>
.noise__summary {
  margin: 0 0 0.75rem;
}

.noise__sources {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0 0 1rem;
  padding: 0;
  list-style: none;
}

.noise__list {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.noise__item {
  display: grid;
  gap: 0.5rem;
  padding: 1rem 0;
}

.noise__item + .noise__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.noise__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.noise__name {
  min-width: 0;
  overflow-wrap: anywhere;
}

.noise__count {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* The share of all the alerts, as a bar the width of the card: the figures beside it say the
   same, so it is only for the eye. */
.noise__bar {
  height: 0.5rem;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(var(--v-theme-on-surface), 0.08);
}

.noise__bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--noise-accent);
}

.noise__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.noise__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
