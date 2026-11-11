<script setup lang="ts">
import { CircleCheck, Plus, RefreshCw, ShieldCheck, Sparkles } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchSuggestions,
  fetchTrust,
  revokeTrust,
  trust,
  type Suggestion,
  type Trust,
  type TrustList,
} from '@/api/trust'
import AppPage from '@/components/AppPage.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import StatTile from '@/components/StatTile.vue'
import TrustDialog from '@/components/TrustDialog.vue'
import TrustRow from '@/components/TrustRow.vue'
import { formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { LEVEL } from '@/trust'

/**
 * Trust: what you have told AresGate is safe, in one place. Each decision keeps what it matches
 * from ever raising an alarm, whichever program reports it. The page lists them, says what each
 * has kept quiet, opens one to change all of it, takes one back, and offers what the AI is sure
 * is nothing to worry about. Trusting something from the page of an incident or a threat leads
 * here.
 */
const session = useSessionStore()

const list = ref<TrustList | null>(null)
const suggestions = ref<Suggestion[]>([])
const loadError = ref<string | null>(null)
const loading = ref(false)
const search = ref('')

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = ref(false)
/** The decision being taken back. The dialog keeps showing it while it fades out. */
const target = ref<Trust | null>(null)
const confirming = ref(false)
const adding = ref(false)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    list.value = await session.call(fetchTrust)
    // What the AI suggests is an extra: the page stands without it.
    suggestions.value = await session.call(fetchSuggestions).catch(() => [])
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

/** The decisions that match the words typed in the search, in what they say, their note or their level. */
function matching(items: Trust[]): Trust[] {
  const words = search.value.trim().toLowerCase()
  if (!words) return items
  return items.filter((rule) =>
    [rule.about, rule.note ?? '', LEVEL[rule.verdict].label].some((text) =>
      text.toLowerCase().includes(words),
    ),
  )
}

function ask(rule: Trust) {
  target.value = rule
  notice.value = null
  failure.value = null
  confirming.value = true
}

async function takeBack() {
  const rule = target.value as Trust
  busy.value = true
  failure.value = null
  try {
    await session.change((token) => revokeTrust(rule.id, token))
    notice.value = `Taken back: ${rule.about}.`
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    confirming.value = false
  }
}

async function accept(suggestion: Suggestion) {
  failure.value = null
  try {
    await session.change((token) =>
      trust(
        {
          address: suggestion.subject,
          verdict: suggestion.verdict,
          note: suggestion.reason ?? suggestion.headline,
        },
        token,
      ),
    )
    notice.value = `Trusted everything about ${suggestion.subject}.`
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
  }
}

async function added(rule: Trust) {
  notice.value = `Trusted: ${rule.about}.`
  await load()
}

onMounted(load)
</script>

<template>
  <AppPage width="wide" class="trust">
    <PageHeader
      title="Trust"
      description="What you have told AresGate is safe. It never raises an alarm about it, whichever program reports it."
    >
      <template #icon>
        <v-icon :icon="ShieldCheck" size="32" />
      </template>
      <template #actions>
        <v-btn color="primary" :prepend-icon="Plus" data-test="add-trust" @click="adding = true">
          Trust something
        </v-btn>
      </template>
    </PageHeader>

    <v-alert type="info" variant="tonal" class="trust__info" data-test="trust-info">
      <p class="text-title-medium">How trust works</p>
      <p class="text-body-large">
        A decision here applies to every signal that matches it, from OPNsense, Wazuh, ntopng and
        CrowdSec alike, now and from here on. A device you trust to talk to a service is only
        trusted for what it sends there: an attack aimed at it still counts. Open a decision to
        change all of it, or take it back and the alerts are judged as if you had never said it.
      </p>
    </v-alert>

    <output v-if="notice" class="trust__notice text-body-large" data-test="trust-notice">
      <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
      {{ notice }}
    </output>
    <v-alert v-if="failure" type="error" variant="tonal" data-test="trust-failure">
      {{ failure }}
    </v-alert>

    <LoadError
      v-if="loadError && !list"
      :message="loadError"
      :loading="loading"
      data-test="trust-error"
      @retry="load"
    />
    <template v-else-if="list">
      <div class="trust__tiles" data-test="trust-tiles">
        <StatTile
          label="Trusted"
          :value="formatCount(list.items.length)"
          hint="decisions in force"
          :icon="ShieldCheck"
        />
        <StatTile label="Safe" :value="formatCount(list.safe)" hint="never alarms" />
        <StatTile
          label="Low priority"
          :value="formatCount(list.low_priority)"
          hint="a glance, not an alarm"
        />
        <StatTile
          label="Kept quiet"
          :value="formatCount(list.applied)"
          hint="alerts they have kept from alarming"
          tone="good"
        />
      </div>

      <SectionCard
        v-if="suggestions.length"
        title="The AI would trust these"
        description="Incidents the AI read and is sure are nothing to worry about, and that nothing trusts yet. Trusting one is your call, and you can take it back."
        data-test="suggestions-card"
      >
        <ul class="trust__suggestions">
          <li
            v-for="suggestion in suggestions"
            :key="suggestion.incident_id"
            class="suggestion"
            data-test="suggestion"
          >
            <div class="suggestion__text">
              <p class="text-title-medium suggestion__headline">
                <v-icon :icon="Sparkles" size="18" aria-hidden="true" />
                {{ suggestion.headline }}
              </p>
              <p class="text-body-medium text-medium-emphasis">
                {{ suggestion.subject }}, {{ suggestion.confidence }}% sure it is
                {{ LEVEL[suggestion.verdict].label.toLowerCase() }}.
                {{ suggestion.reason ?? '' }}
              </p>
            </div>
            <SeverityChip :severity="suggestion.severity" />
            <div class="suggestion__actions">
              <v-btn
                variant="text"
                size="small"
                :to="{ name: 'incident', params: { id: suggestion.incident_id } }"
                :aria-label="`Look at ${suggestion.subject} first`"
                data-test="suggestion-open"
              >
                Look first
              </v-btn>
              <v-btn
                variant="tonal"
                color="success"
                size="small"
                :prepend-icon="ShieldCheck"
                :aria-label="`Trust ${suggestion.subject}`"
                data-test="suggestion-trust"
                @click="accept(suggestion)"
              >
                Trust
              </v-btn>
            </div>
          </li>
        </ul>
      </SectionCard>

      <SectionCard
        title="What you trust"
        description="The one changed last comes first."
        data-test="trust-card"
      >
        <template #actions>
          <v-btn
            variant="text"
            :prepend-icon="RefreshCw"
            :loading="loading"
            data-test="refresh-trust"
            @click="load"
          >
            Refresh
          </v-btn>
        </template>
        <v-text-field
          v-if="list.items.length > 1"
          v-model="search"
          label="Search what you trust"
          clearable
          hide-details
          density="comfortable"
          class="trust__search"
          data-test="trust-search"
        />
        <ul v-if="matching(list.items).length" class="trust__list" data-test="trust-list">
          <TrustRow
            v-for="rule in matching(list.items)"
            :key="rule.id"
            :rule="rule"
            @revoke="ask(rule)"
          />
        </ul>
        <EmptyState
          v-else-if="list.items.length"
          title="Nothing you trust matches that"
          description="Try other words, or clear the search."
          data-test="trust-none-found"
        />
        <EmptyState
          v-else
          title="You haven't trusted anything yet"
          description="When something is marked as a threat and you know it is fine (a camera talking to its cloud, a scanner of your own), trust it from its incident or from here, and AresGate stops raising alarms about it."
          :icon="ShieldCheck"
          data-test="no-trust"
        >
          <v-btn
            variant="tonal"
            color="primary"
            :to="{ name: 'incidents' }"
            data-test="see-incidents"
          >
            See incidents
          </v-btn>
        </EmptyState>
      </SectionCard>
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="trust-loading" />

    <TrustDialog v-model="adding" @trusted="added" />
    <ConfirmDialog
      v-model="confirming"
      title="Take this back?"
      confirm-label="Take it back"
      destructive
      :busy="busy"
      @confirm="takeBack"
    >
      <template v-if="target">
        <p class="mb-2">{{ target.about }}</p>
        <p>
          It is judged as if you had never said it, which means it can raise alarms again.
          {{
            target.hits > 0
              ? `${formatCount(target.hits)} ${target.hits === 1 ? 'alert' : 'alerts'} it kept quiet ${target.hits === 1 ? 'is' : 'are'} judged again in the incidents that are not resolved.`
              : 'It has not been applied to an alert yet.'
          }}
        </p>
      </template>
    </ConfirmDialog>
  </AppPage>
</template>

<style scoped>
.trust :deep(p) {
  margin: 0;
}

.trust__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
  gap: 0.75rem;
}

.trust__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.trust__search {
  margin-block-end: 0.75rem;
}

.trust__list,
.trust__suggestions {
  margin: 0;
  padding: 0;
  list-style: none;
}

.suggestion {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding-block: 0.75rem;
  border-block-start: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.suggestion:first-child {
  border-block-start: 0;
}

.suggestion__headline {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.suggestion__actions {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
}

@media (min-width: 960px) {
  .suggestion {
    grid-template-columns: minmax(0, 1fr) auto auto;
  }

  .suggestion__actions {
    grid-column: auto;
  }
}
</style>
