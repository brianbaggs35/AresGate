<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import type { OwnerCall } from '@/api/incidents'
import { callFamily, fetchFamily, judgeFamily, type FamilyDetail } from '@/api/threats'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import FamilyJudgement from '@/components/FamilyJudgement.vue'
import IncidentCard from '@/components/IncidentCard.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'
import { reachOf } from '@/threats'

/**
 * One kind of incident: the incidents that programs reported in the same words about the same
 * sort of place, what you and the AI make of all of them, why, and the incidents themselves.
 * Where the Threats page says what is set aside, this is where you check and overrule it.
 */
const REFRESH_SECONDS = 30

const session = useSessionStore()
const route = useRoute()
const id = computed(() => Number(route.params.id))

const family = ref<FamilyDetail | null>(null)
const loadError = ref<string | null>(null)
/** The kind isn't there, which asking again won't change. */
const missing = ref(false)
const loading = ref(false)
const asking = ref(false)
const calling = ref<OwnerCall | 'clear' | null>(null)
const failure = ref<string | null>(null)
let latest = 0

async function load(quiet = false) {
  const mine = ++latest
  if (!quiet) loading.value = true
  try {
    const found = await session.call(() => fetchFamily(id.value))
    // Something being changed will answer with a newer one.
    if (mine !== latest || asking.value || calling.value) return
    family.value = found
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

/** Keeps your word on the kind, or takes it back. */
async function call(word: OwnerCall | null) {
  calling.value = word ?? 'clear'
  failure.value = null
  try {
    const kept = await session.change((token) => callFamily(id.value, word, token))
    latest += 1
    family.value = kept
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    calling.value = null
  }
}

/** Has the AI judge it now. Whatever comes of it, the page says: the answer, or why there is none. */
async function ask() {
  asking.value = true
  failure.value = null
  try {
    const result = await session.change((token) => judgeFamily(id.value, token))
    latest += 1
    family.value = result.family
    failure.value = result.ok ? null : result.reason
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    asking.value = false
  }
}

// Read only once the kind is shown.
const reach = computed(() => reachOf((family.value as FamilyDetail).reach))

onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="wide" class="kind">
    <template v-if="family">
      <PageHeader
        :title="family.label"
        :description="`${reach.label}, seen by ${family.source_name}.`"
        :back="{ to: { name: 'kinds' }, label: 'Kinds of incident' }"
      />

      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="kind-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>

      <FamilyJudgement
        :family="family"
        :asking="asking"
        :calling="calling"
        :failure="failure"
        @call="call"
        @ask="ask"
      />

      <SectionCard
        v-if="family.why.length"
        title="Why they are where they are"
        description="What decides the lane of the incidents of this kind."
        data-test="why-card"
      >
        <ul class="kind__why text-body-large">
          <li v-for="line in family.why" :key="line" data-test="why">{{ line }}</li>
        </ul>
      </SectionCard>

      <section aria-labelledby="sample-title" class="kind__sample" data-test="sample">
        <header class="kind__head">
          <div>
            <h2 id="sample-title" class="text-title-large">Its incidents</h2>
            <p class="text-body-medium text-medium-emphasis">
              {{ formatCount(family.incidents) }}
              {{ family.incidents === 1 ? 'incident is' : 'incidents are' }} going on,
              {{ formatCount(family.alerts) }} {{ family.alerts === 1 ? 'alert' : 'alerts' }} in all
              from {{ formatCount(family.actors) }}
              {{ family.actors === 1 ? 'address' : 'addresses' }}.
            </p>
          </div>
          <v-btn
            variant="text"
            :append-icon="ArrowRight"
            :to="{ name: 'incidents', query: { family: String(family.id) } }"
            data-test="sample-all"
          >
            Open them in Incidents
          </v-btn>
        </header>
        <ul v-if="family.sample.length" class="kind__list">
          <li v-for="incident in family.sample" :key="incident.id">
            <IncidentCard :incident="incident" @judged="load(true)" />
          </li>
        </ul>
        <EmptyState
          v-else
          title="No incidents of this kind are going on"
          description="They are over, or you have handled them. The kind stays, and your word on it with it."
          data-test="sample-empty"
        />
      </section>
    </template>
    <template v-else-if="loadError">
      <PageHeader
        title="Kind of incident"
        :back="{ to: { name: 'kinds' }, label: 'Kinds of incident' }"
      />
      <LoadError
        :message="missing ? `${loadError} It may have been removed.` : loadError"
        :can-retry="!missing"
        :loading="loading"
        data-test="kind-error"
        @retry="load()"
      />
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="kind-loading" />
  </AppPage>
</template>

<style scoped>
.kind__why {
  margin: 0;
  padding-inline-start: 1.25rem;
}

.kind__sample {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.kind__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.kind__head h2,
.kind__head p {
  margin: 0;
}

.kind__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
