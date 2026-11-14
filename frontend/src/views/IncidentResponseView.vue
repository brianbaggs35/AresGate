<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchIncidentResponse,
  type ResponseGroup,
  type ResponseOverview,
  type ResponseRange,
} from '@/api/incidentResponse'
import AppPage from '@/components/AppPage.vue'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import HeroSurface from '@/components/HeroSurface.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import ResponseRow from '@/components/ResponseRow.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount } from '@/format'
import { coverage, GROUPS, headline, RANGES } from '@/incidentResponse'
import { useSessionStore } from '@/stores/session'

/**
 * Incident Response, under Incidents in the menu: what was done about the incidents of the last
 * few days. A sentence says whether any still waits for a response, and under it each incident
 * is in the one group that says what was done about it (waiting, banned, turned away, ban ended),
 * those that wait first. Only incidents of medium severity or higher count, and not those the
 * owner called harmless or dismissed. What is read is CrowdSec's bans, the firewall's blocks and
 * what Suricata stopped, so it says what it cannot see when one of those isn't connected.
 */
const session = useSessionStore()

/** How many of a group are listed before the rest are behind a button. */
const FIRST = 10

const range = ref<ResponseRange>('7d')
const overview = ref<ResponseOverview | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
/** The groups whose every incident is listed, not just the first few. */
const expanded = ref<ReadonlySet<string>>(new Set())
/** Which load is the newest, so the answer to an older one (for another range) is dropped. */
let latest = 0

async function load() {
  const mine = ++latest
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(() => fetchIncidentResponse(range.value))
    if (mine !== latest) return
    overview.value = found
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

function pick(next: ResponseRange) {
  range.value = next
  expanded.value = new Set()
  void load()
}

function showAll(group: ResponseGroup) {
  expanded.value = new Set([...expanded.value, group.key])
}

const words = computed(
  () => RANGES.find(({ key }) => key === range.value) as (typeof RANGES)[number],
)
const shown = computed(() => overview.value as ResponseOverview)
const said = computed(() => headline(shown.value, words.value.long))
const unseen = computed(() => coverage(shown.value))
/** The groups with something in them: an empty one has nothing to say. */
const filled = computed(() => shown.value.groups.filter((group) => group.items.length > 0))
const waiting = computed(() => shown.value.groups.find((group) => group.key === 'needs_response'))

function listed(group: ResponseGroup) {
  return expanded.value.has(group.key) ? group.items : group.items.slice(0, FIRST)
}

onMounted(load)
</script>

<template>
  <AppPage width="regular" class="incident-response">
    <PageHeader
      title="Incident response"
      description="What was done about the incidents of medium severity or higher, and which still wait for a response."
    >
      <template v-if="overview" #actions>
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
      v-if="loadError && !overview"
      :message="loadError"
      :loading="loading"
      data-test="response-error"
      @retry="load"
    />
    <template v-else-if="overview">
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="response-stale">
        {{ loadError }} What is shown is from before.
      </v-alert>

      <HeroSurface
        test-id="response-hero"
        :data-tone="said.tone"
        :tone="said.color"
        :icon="said.icon"
        :eyebrow="said.eyebrow"
        :title="said.title"
        :detail="said.detail"
        :mood="said.tone === 'urgent' ? 'urgent' : said.tone === 'idle' ? 'idle' : 'calm'"
      >
        <ul v-if="filled.length" class="counts" aria-label="How they were answered">
          <li v-for="group in filled" :key="group.key">
            <v-chip
              :color="GROUPS[group.key].color"
              :prepend-icon="GROUPS[group.key].icon"
              variant="tonal"
              :data-test="`count-${group.key}`"
            >
              {{ group.label }}: {{ formatCount(group.items.length) }}
            </v-chip>
          </li>
        </ul>
      </HeroSurface>

      <v-alert v-if="unseen" type="info" variant="tonal" data-test="response-coverage">
        {{ unseen }}
        <template #append>
          <v-btn variant="text" :to="{ name: 'integrations' }" data-test="response-connect">
            Integrations
          </v-btn>
        </template>
      </v-alert>

      <SectionCard
        v-if="waiting && waiting.items.length === 0 && filled.length > 0"
        title="Needs a response"
        :description="waiting.description"
        data-test="group-needs_response"
      >
        <p class="text-body-large" data-test="response-none-waiting">
          Nothing is waiting for a response.
        </p>
      </SectionCard>

      <SectionCard
        v-for="group in filled"
        :key="group.key"
        :title="`${group.label} (${formatCount(group.items.length)})`"
        :description="group.description"
        :data-test="`group-${group.key}`"
      >
        <ul class="list">
          <ResponseRow v-for="item in listed(group)" :key="item.id" :item="item" />
        </ul>
        <v-btn
          v-if="group.items.length > FIRST && !expanded.has(group.key)"
          variant="tonal"
          class="mt-3"
          :data-test="`more-${group.key}`"
          @click="showAll(group)"
        >
          Show {{ formatCount(group.items.length - FIRST) }} more
        </v-btn>
      </SectionCard>

      <p
        v-if="overview.total > overview.shown"
        class="text-body-medium text-medium-emphasis"
        data-test="response-capped"
      >
        Showing the {{ formatCount(overview.shown) }} most serious of
        {{ formatCount(overview.total) }} incidents.
      </p>
      <p class="text-body-medium text-medium-emphasis" data-test="response-scope">
        Incidents of {{ overview.minimum }} severity or higher that went on in {{ words.long }},
        except those you called not suspicious or low priority, and dismissed ones. A ban is dated
        by when AresGate first read it.
      </p>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="response-loading" />
  </AppPage>
</template>

<style scoped>
.counts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
