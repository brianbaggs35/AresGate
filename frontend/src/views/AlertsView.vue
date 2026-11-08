<script setup lang="ts">
import { BellOff, BellRing, CircleCheck, Plus } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import {
  addDestination,
  changeDestination,
  changeRules,
  fetchDestinations,
  removeDestination,
  testDestination,
  type Destination,
  type Destinations,
  type Rules,
} from '@/api/alerts'
import { ApiError, errorMessage } from '@/api/client'
import { problemsByField } from '@/ai'
import AppPage from '@/components/AppPage.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DeliveryLog from '@/components/DeliveryLog.vue'
import DestinationCard from '@/components/DestinationCard.vue'
import DestinationDialog from '@/components/DestinationDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import RulesDialog from '@/components/RulesDialog.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Where AresGate tells the owner about threats. For now that is Discord: each destination is a
 * webhook for one channel, kept encrypted and never shown again, with a button that sends a real
 * test message, and rules for what each one is told about and when. Adding, changing, setting
 * the rules of, turning off and removing a destination all happen here.
 */
const session = useSessionStore()

const listing = ref<Destinations | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
/** The destination something is being done to, so its buttons wait. */
const working = ref<number | null>(null)
const testing = ref<number | null>(null)

/** The destination being changed or removed, or none for a new one. The dialogs keep showing it
 * while they fade out. */
const target = ref<Destination | null>(null)
const editing = ref(false)
const confirming = ref(false)
const saving = ref(false)
const problems = ref<Record<string, string>>({})
const formFailure = ref<string | null>(null)

/** The destination whose rules are open, which the sheet keeps showing while it fades out. */
const ruling = ref<Destination | null>(null)
const rulesOpen = ref(false)
const rulesSaving = ref(false)
const rulesProblems = ref<Record<string, string>>({})
const rulesFailure = ref<string | null>(null)

// These are only read once the list has loaded: the page shows nothing that uses them before.
const items = computed(() => (listing.value as Destinations).items)
const full = computed(() => items.value.length >= (listing.value as Destinations).max_destinations)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    listing.value = await session.call(fetchDestinations)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

function keep(kept: Destination[]) {
  listing.value = { ...(listing.value as Destinations), items: kept }
}

function replace(saved: Destination) {
  keep(items.value.map((item) => (item.id === saved.id ? saved : item)))
}

function begin() {
  notice.value = null
  failure.value = null
}

function add() {
  target.value = null
  problems.value = {}
  formFailure.value = null
  editing.value = true
}

function edit(destination: Destination) {
  target.value = destination
  problems.value = {}
  formFailure.value = null
  editing.value = true
}

function rules(destination: Destination) {
  begin()
  ruling.value = destination
  rulesProblems.value = {}
  rulesFailure.value = null
  rulesOpen.value = true
}

async function saveRules(answer: Rules) {
  const destination = ruling.value as Destination
  rulesSaving.value = true
  rulesProblems.value = {}
  rulesFailure.value = null
  try {
    const saved = await session.change((token) => changeRules(destination.id, answer, token))
    replace(saved)
    notice.value = `Saved what ${saved.name} is told.`
    rulesOpen.value = false
  } catch (error) {
    if (error instanceof ApiError && error.problems.length > 0) {
      rulesProblems.value = problemsByField(error.problems)
    } else {
      rulesFailure.value = errorMessage(error)
    }
  } finally {
    rulesSaving.value = false
  }
}

function ask(destination: Destination) {
  begin()
  target.value = destination
  confirming.value = true
}

async function save(answer: { name: string; url: string }) {
  const destination = target.value
  saving.value = true
  problems.value = {}
  formFailure.value = null
  try {
    if (destination) {
      const change = { name: answer.name, ...(answer.url ? { url: answer.url } : {}) }
      const saved = await session.change((token) =>
        changeDestination(destination.id, change, token),
      )
      replace(saved)
      notice.value = `Saved ${saved.name}.`
    } else {
      const saved = await session.change((token) => addDestination(answer, token))
      keep([...items.value, saved])
      notice.value = `Added ${saved.name}. Send a test message to check it reaches the channel.`
    }
    editing.value = false
  } catch (error) {
    if (error instanceof ApiError && error.problems.length > 0) {
      problems.value = problemsByField(error.problems)
    } else {
      formFailure.value = errorMessage(error)
    }
  } finally {
    saving.value = false
  }
}

async function test(destination: Destination) {
  begin()
  testing.value = destination.id
  try {
    const answer = await session.change((token) => testDestination(destination.id, token))
    replace(answer.destination)
    // A failure is shown on the card, which carries what went wrong.
    if (answer.ok)
      notice.value = `Test message sent to ${destination.name}. Look for it in the channel.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    testing.value = null
  }
}

async function toggle(destination: Destination, enabled: boolean) {
  begin()
  working.value = destination.id
  try {
    replace(await session.change((token) => changeDestination(destination.id, { enabled }, token)))
    notice.value = enabled
      ? `${destination.name} will be sent alerts.`
      : `${destination.name} will not be sent anything.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    working.value = null
  }
}

async function remove() {
  const destination = target.value as Destination
  saving.value = true
  try {
    await session.change((token) => removeDestination(destination.id, token))
    keep(items.value.filter((item) => item.id !== destination.id))
    notice.value = `Removed ${destination.name}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
    confirming.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppPage width="regular">
    <PageHeader
      title="Alerts"
      description="Where AresGate tells you about threats. Add a Discord channel and it posts there when something needs your attention."
    >
      <template #icon>
        <BellRing :size="28" />
      </template>
      <template v-if="listing" #actions>
        <v-btn
          color="primary"
          variant="flat"
          :prepend-icon="Plus"
          :disabled="full"
          data-test="destination-add"
          @click="add"
        >
          Add destination
        </v-btn>
      </template>
    </PageHeader>

    <output v-if="notice" class="alerts__notice text-body-large" data-test="alerts-notice">
      <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
      {{ notice }}
    </output>
    <v-alert v-if="failure" type="error" variant="tonal" data-test="alerts-failure">
      {{ failure }}
    </v-alert>

    <LoadError
      v-if="loadError && !listing"
      :message="loadError"
      :loading="loading"
      retry-test-id="alerts-retry"
      data-test="alerts-error"
      @retry="load"
    />
    <SectionCard
      v-else-if="listing"
      title="Destinations"
      description="Each is a webhook for one Discord channel. Its address is a secret: it is kept encrypted and never shown again."
    >
      <ul v-if="items.length" class="alerts__list" data-test="destination-list">
        <DestinationCard
          v-for="item in items"
          :key="item.id"
          :destination="item"
          :choices="listing.choices"
          :busy="working === item.id || testing === item.id"
          :testing="testing === item.id"
          @test="test(item)"
          @rules="rules(item)"
          @edit="edit(item)"
          @remove="ask(item)"
          @toggle="toggle(item, $event)"
        />
      </ul>
      <EmptyState
        v-else
        title="No alerts are set up"
        description="AresGate watches your network, but it has nowhere to tell you. Add the webhook of a Discord channel and it can post there."
        :icon="BellOff"
        data-test="no-destinations"
      >
        <v-btn
          color="primary"
          variant="flat"
          :prepend-icon="Plus"
          data-test="empty-add"
          @click="add"
        >
          Add a Discord channel
        </v-btn>
      </EmptyState>
      <p v-if="full" class="text-body-medium text-medium-emphasis mt-4" data-test="alerts-full">
        You have {{ listing.max_destinations }} destinations, which is the most AresGate keeps.
        Remove one to add another.
      </p>
    </SectionCard>
    <v-skeleton-loader v-else type="card" />
    <DeliveryLog v-if="listing && items.length" :destinations="items" />

    <DestinationDialog
      v-model="editing"
      :destination="target"
      :busy="saving"
      :problems="problems"
      :failure="formFailure"
      @save="save"
    />
    <RulesDialog
      v-if="listing && ruling"
      v-model="rulesOpen"
      :destination="ruling"
      :choices="listing.choices"
      :busy="rulesSaving"
      :problems="rulesProblems"
      :failure="rulesFailure"
      @save="saveRules"
    />
    <ConfirmDialog
      v-model="confirming"
      title="Remove this destination?"
      confirm-label="Remove it"
      destructive
      :busy="saving"
      @confirm="remove"
    >
      <template v-if="target">
        <p class="mb-2">{{ target.name }}</p>
        <p>
          AresGate forgets its webhook address and sends it nothing more. The webhook stays in
          Discord until you delete it there.
        </p>
      </template>
    </ConfirmDialog>
  </AppPage>
</template>

<style scoped>
.alerts__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.alerts__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
