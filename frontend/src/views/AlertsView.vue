<script setup lang="ts">
import { BellOff, BellRing, CircleCheck, Plus } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import {
  addDestination,
  changeDestination,
  changeRules,
  fetchDestinations,
  removeDestination,
  removeMailServer,
  saveMailServer,
  sendSample,
  testDestination,
  type Destination,
  type DestinationChange,
  type DestinationKind,
  type Destinations,
  type MailServerChange,
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
import MailServerCard from '@/components/MailServerCard.vue'
import MailServerDialog from '@/components/MailServerDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import RulesDialog from '@/components/RulesDialog.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Where AresGate tells the owner about threats: a Discord channel, reached with a webhook, or an
 * email address, reached through the mail server set up here. A webhook's address and the mail
 * server's password are kept encrypted and never shown again. Each destination has a button that
 * sends a real test message, and rules for what it is told about and when. Adding, changing,
 * setting the rules of, turning off and removing a destination, and setting up the mail server,
 * all happen here.
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
const sampling = ref<number | null>(null)

/** The destination being changed or removed, or none for a new one. The dialogs keep showing it
 * while they fade out. */
const target = ref<Destination | null>(null)
const editing = ref(false)
const confirming = ref(false)
const saving = ref(false)
const problems = ref<Record<string, string>>({})
const formFailure = ref<string | null>(null)

/** The destination whose rules are open, which the sheet keeps showing while it fades out. */
const mailing = ref(false)
const mailRemoving = ref(false)
const mailSaving = ref(false)
const mailProblems = ref<Record<string, string>>({})
const mailFailure = ref<string | null>(null)

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

/** Where a message goes, in words, for the notices. */
function whereOf(destination: Destination): string {
  return destination.kind === 'email'
    ? `the inbox of ${destination.recipient ?? destination.name}`
    : 'the channel'
}

async function save(answer: {
  kind: DestinationKind
  name: string
  url: string
  recipient: string
}) {
  const destination = target.value
  saving.value = true
  problems.value = {}
  formFailure.value = null
  try {
    if (destination) {
      const change: DestinationChange = { name: answer.name }
      if (answer.url) change.url = answer.url
      if (answer.recipient) change.recipient = answer.recipient
      const saved = await session.change((token) =>
        changeDestination(destination.id, change, token),
      )
      replace(saved)
      notice.value = `Saved ${saved.name}.`
    } else {
      const add =
        answer.kind === 'email'
          ? { kind: answer.kind, name: answer.name, recipient: answer.recipient }
          : { kind: answer.kind, name: answer.name, url: answer.url }
      const saved = await session.change((token) => addDestination(add, token))
      keep([...items.value, saved])
      notice.value = `Added ${saved.name}. Send a test message to check it reaches ${whereOf(saved)}.`
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
      notice.value = `Test message sent to ${destination.name}. Look for it in ${whereOf(destination)}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    testing.value = null
  }
}

async function sample(destination: Destination) {
  begin()
  sampling.value = destination.id
  try {
    const answer = await session.change((token) => sendSample(destination.id, token))
    replace(answer.destination)
    if (answer.ok)
      notice.value = `A sample alert was sent to ${destination.name}. Look for it in ${whereOf(destination)}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    sampling.value = null
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

function setUpMail() {
  begin()
  mailProblems.value = {}
  mailFailure.value = null
  mailing.value = true
}

async function saveMail(answer: MailServerChange) {
  mailSaving.value = true
  mailProblems.value = {}
  mailFailure.value = null
  try {
    await session.change((token) => saveMailServer(answer, token))
    notice.value =
      'Saved the mail server. Send a test message from an email destination to check it.'
    mailing.value = false
    // Saving the settings lets the email destinations try again, so how they stand has changed.
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.problems.length > 0) {
      mailProblems.value = problemsByField(error.problems)
    } else {
      mailFailure.value = errorMessage(error)
    }
  } finally {
    mailSaving.value = false
  }
}

function askAboutMail() {
  begin()
  mailRemoving.value = true
}

async function removeMail() {
  mailSaving.value = true
  try {
    await session.change((token) => removeMailServer(token))
    notice.value = 'Removed the mail server. Email destinations wait until another is set up.'
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    mailSaving.value = false
    mailRemoving.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppPage width="regular">
    <PageHeader
      title="Alerts"
      description="Where AresGate tells you about threats. Add a Discord channel or an email address and it tells you there when something needs your attention."
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
      description="Each is a Discord channel, reached with a webhook, or an email address. A webhook's address is a secret: it is kept encrypted and never shown again."
    >
      <ul v-if="items.length" class="alerts__list" data-test="destination-list">
        <DestinationCard
          v-for="item in items"
          :key="item.id"
          :destination="item"
          :choices="listing.choices"
          :busy="working === item.id || testing === item.id || sampling === item.id"
          :testing="testing === item.id"
          :sampling="sampling === item.id"
          @test="test(item)"
          @sample="sample(item)"
          @rules="rules(item)"
          @edit="edit(item)"
          @remove="ask(item)"
          @toggle="toggle(item, $event)"
        />
      </ul>
      <EmptyState
        v-else
        title="No alerts are set up"
        description="AresGate watches your network, but it has nowhere to tell you. Add the webhook of a Discord channel, or an email address, and it can tell you there."
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
          Add a destination
        </v-btn>
      </EmptyState>
      <p v-if="full" class="text-body-medium text-medium-emphasis mt-4" data-test="alerts-full">
        You have {{ listing.max_destinations }} destinations, which is the most AresGate keeps.
        Remove one to add another.
      </p>
    </SectionCard>
    <v-skeleton-loader v-else type="card" />
    <SectionCard
      v-if="listing"
      title="Mail server"
      description="Email destinations send through this server. Its password is kept encrypted and never shown again."
      data-test="mail-section"
    >
      <MailServerCard
        :server="listing.smtp"
        :busy="mailSaving"
        @edit="setUpMail"
        @remove="askAboutMail"
      />
    </SectionCard>
    <DeliveryLog v-if="listing && items.length" :destinations="items" />

    <DestinationDialog
      v-model="editing"
      :destination="target"
      :busy="saving"
      :mail-ready="listing?.smtp.configured ?? false"
      :problems="problems"
      :failure="formFailure"
      @save="save"
    />
    <MailServerDialog
      v-if="listing"
      v-model="mailing"
      :server="listing.smtp"
      :busy="mailSaving"
      :problems="mailProblems"
      :failure="mailFailure"
      @save="saveMail"
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
        <p v-if="target.kind === 'email'">
          AresGate sends nothing more to {{ target.recipient }}. The mail server stays as it is.
        </p>
        <p v-else>
          AresGate forgets its webhook address and sends it nothing more. The webhook stays in
          Discord until you delete it there.
        </p>
      </template>
    </ConfirmDialog>
    <ConfirmDialog
      v-model="mailRemoving"
      title="Remove the mail server?"
      confirm-label="Remove it"
      destructive
      :busy="mailSaving"
      @confirm="removeMail"
    >
      <p>
        AresGate forgets the mail server and its password. Email destinations are kept, but send
        nothing until you set up a mail server again.
      </p>
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
