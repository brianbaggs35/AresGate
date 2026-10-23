<script setup lang="ts">
import { ArrowLeft, ExternalLink, FlaskConical, Plug, Unplug } from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import {
  disconnectIntegration,
  fetchIntegration,
  saveIntegration,
  testIntegration,
  type CheckReport,
  type Integration,
} from '@/api/integrations'
import ApiLog from '@/components/ApiLog.vue'
import ConnectionCard from '@/components/ConnectionCard.vue'
import StatusChip from '@/components/StatusChip.vue'
import { formatAgo, formatDateTime } from '@/format'
import {
  draftFrom,
  connectionLabels,
  fieldId,
  integrationIcon,
  settingsFrom,
  sortProblems,
  type ConnectionDraft,
  type FieldProblems,
} from '@/integrations'
import { useSessionStore } from '@/stores/session'

/** What the page is doing, so only one thing is asked of the API at a time. */
type Busy = 'saving' | 'testing' | 'disconnecting'

const route = useRoute()
const session = useSessionStore()

const key = computed(() => String(route.params.key))

const integration = ref<Integration | null>(null)
const loadError = ref<{ message: string; missing: boolean } | null>(null)
/** The form for each connection, by its key. */
const drafts = ref<Record<string, ConnectionDraft>>({})
/** How the forms were when they were last loaded or saved, to tell when they have changed. */
const untouched = ref('')

const busy = ref<Busy | null>(null)
const problems = ref<FieldProblems>({})
const otherProblems = ref<string[]>([])
const failure = ref<string | null>(null)
const report = ref<CheckReport | null>(null)
const notice = ref<string | null>(null)
const confirming = ref(false)
/** Counts what made requests to the integration, so the log reloads. */
const requests = ref(0)
/** The setup guide is open while there is nothing connected yet. */
const guide = ref<number | undefined>(undefined)

const summary = ref<HTMLElement | null>(null)
const confirmation = ref<HTMLElement | null>(null)
const disconnectButton = ref<{ $el: HTMLElement } | null>(null)

const connected = computed(() => integration.value?.status !== 'not_connected')
const changed = computed(() => JSON.stringify(drafts.value) !== untouched.value)
const hasProblems = computed(
  () => Object.keys(problems.value).length > 0 || otherProblems.value.length > 0,
)
/** Starts the forms from how the integration is saved. */
function adopt(next: Integration) {
  integration.value = next
  drafts.value = Object.fromEntries(
    next.connections.map((connection) => [connection.definition.key, draftFrom(connection)]),
  )
  untouched.value = JSON.stringify(drafts.value)
  document.title = `${next.name} · Integrations · AresGate`
}

/** The connections as the log lists them, to tell its requests apart. */
const logConnections = (current: Integration) =>
  Object.entries(connectionLabels(current)).map(([key, label]) => ({ key, label }))

function clearFeedback() {
  problems.value = {}
  otherProblems.value = []
  failure.value = null
  report.value = null
  notice.value = null
}

async function load() {
  loadError.value = null
  try {
    const next = await session.call(() => fetchIntegration(key.value))
    adopt(next)
    guide.value = next.status === 'not_connected' ? 0 : undefined
  } catch (error) {
    loadError.value = {
      message: errorMessage(error),
      missing: error instanceof ApiError && error.code === 'not_found',
    }
  }
}

/** Moves the keyboard to the first field that has something wrong with it, or to the summary
 * of the problems when that is a choice or something else with no field of its own. */
async function focusFirstProblem() {
  await nextTick()
  const wrong = new Set(
    Object.entries(problems.value).flatMap(([connection, fields]) =>
      Object.keys(fields).map((field) => fieldId(connection, field)),
    ),
  )
  const inputs = document.querySelectorAll<HTMLElement>(
    '#integration-form input[id], #integration-form textarea[id]',
  )
  const first = Array.from(inputs).find((input) => wrong.has(input.id))
  ;(first ?? summary.value)?.focus()
}

/** Says why a change failed: field by field when the API could, and in words otherwise. */
async function explain(error: unknown) {
  if (error instanceof ApiError && error.problems.length) {
    const sorted = sortProblems(error.problems)
    problems.value = sorted.fields
    otherProblems.value = sorted.other
    await focusFirstProblem()
  } else {
    failure.value = errorMessage(error)
  }
}

/** One harmless read of each connection, to show it works. Returns why it couldn't be done. */
async function runTest(): Promise<string | null> {
  busy.value = 'testing'
  try {
    const result = await session.change((token) => testIntegration(key.value, token))
    report.value = result
    // Only what testing finds out is taken in: the forms may have something typed in them.
    integration.value = result.integration
    return null
  } catch (error) {
    return errorMessage(error)
  } finally {
    requests.value += 1
    busy.value = null
  }
}

async function test() {
  clearFeedback()
  failure.value = await runTest()
}

async function save(current: Integration) {
  if (busy.value) return
  clearFeedback()
  busy.value = 'saving'
  const settings = Object.fromEntries(
    current.connections.flatMap(({ definition }) => {
      const draft = drafts.value[definition.key]
      return draft?.enabled ? [[definition.key, settingsFrom(definition, draft)]] : []
    }),
  )
  try {
    adopt(await session.change((token) => saveIntegration(key.value, settings, token)))
  } catch (error) {
    busy.value = null
    await explain(error)
    return
  }
  const why = await runTest()
  if (why) failure.value = `Saved, but the test couldn't run. ${why}`
}

async function disconnect(current: Integration) {
  busy.value = 'disconnecting'
  clearFeedback()
  try {
    await session.change((token) => disconnectIntegration(key.value, token))
    confirming.value = false
    adopt(await session.call(() => fetchIntegration(key.value)))
    guide.value = 0
    notice.value = `${current.name} is disconnected. AresGate forgot its addresses and keys.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = null
  }
}

async function cancelDisconnect() {
  confirming.value = false
  await nextTick()
  disconnectButton.value?.$el.focus()
}

watch(confirming, async (asking) => {
  if (!asking) return
  await nextTick()
  confirmation.value?.focus()
})

watch(key, () => {
  integration.value = null
  clearFeedback()
  confirming.value = false
  void load()
})

onMounted(load)
</script>

<template>
  <v-container class="py-6" max-width="900">
    <v-btn
      variant="text"
      :prepend-icon="ArrowLeft"
      :to="{ name: 'integrations' }"
      class="mb-2 ml-n3"
      data-test="back"
    >
      All integrations
    </v-btn>

    <v-card v-if="loadError" class="pa-6" data-test="integration-error">
      <h1 class="text-headline-small mb-2">
        {{ loadError.missing ? 'There is no such integration' : "Couldn't load this integration" }}
      </h1>
      <p class="text-body-large mb-4" data-test="integration-error-message">
        {{ loadError.message }}
      </p>
      <div class="d-flex flex-wrap ga-3">
        <v-btn v-if="!loadError.missing" color="primary" data-test="retry" @click="load">
          Try again
        </v-btn>
        <v-btn variant="tonal" :to="{ name: 'integrations' }">See all integrations</v-btn>
      </div>
    </v-card>

    <v-skeleton-loader
      v-else-if="!integration"
      type="heading, paragraph, card"
      data-test="integration-loading"
    />

    <template v-else>
      <header class="integration__head">
        <span class="integration__icon" aria-hidden="true">
          <component :is="integrationIcon(integration.icon)" :size="30" />
        </span>
        <div class="integration__intro">
          <div class="d-flex flex-wrap align-center ga-3">
            <h1 class="text-headline-medium" data-test="integration-title">
              {{ integration.name }}
            </h1>
            <StatusChip :status="integration.status" />
          </div>
          <p class="text-body-large text-medium-emphasis mt-1" data-test="integration-provides">
            {{ integration.provides }}
          </p>
          <p
            v-if="integration.last_success_at"
            class="text-body-medium text-medium-emphasis"
            data-test="integration-last-success"
          >
            Last successful call
            <time
              :datetime="integration.last_success_at"
              :title="formatDateTime(integration.last_success_at)"
              >{{ formatAgo(integration.last_success_at) }}</time
            >
          </p>
        </div>
        <v-btn
          :href="integration.docs_url"
          target="_blank"
          rel="noopener noreferrer"
          variant="text"
          :append-icon="ExternalLink"
          :aria-label="`${integration.name} documentation (opens in a new tab)`"
          data-test="docs"
        >
          Documentation
        </v-btn>
      </header>

      <v-alert v-if="notice" type="success" variant="tonal" class="mb-6" data-test="notice">
        {{ notice }}
      </v-alert>

      <v-expansion-panels v-model="guide" class="mb-6" data-test="guide">
        <v-expansion-panel title="How to get what you need" elevation="0" border>
          <v-expansion-panel-text>
            <ol class="integration__steps text-body-large">
              <li v-for="step in integration.setup" :key="step">{{ step }}</li>
            </ol>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <form
        id="integration-form"
        novalidate
        data-test="integration-form"
        @submit.prevent="save(integration)"
      >
        <div v-show="hasProblems" ref="summary" tabindex="-1" class="mb-6" data-test="problems">
          <v-alert type="error" variant="tonal" title="Some settings need fixing">
            The fields are marked below.
            <template v-if="otherProblems.length">
              <ul class="mt-2">
                <li v-for="problem in otherProblems" :key="problem">{{ problem }}</li>
              </ul>
            </template>
          </v-alert>
        </div>

        <ConnectionCard
          v-for="connection in integration.connections"
          :key="connection.definition.key"
          v-model="drafts[connection.definition.key]!"
          :integration="integration.key"
          :connection="connection"
          :problems="problems[connection.definition.key] ?? {}"
          class="mb-6"
        />

        <v-alert
          v-if="report"
          :type="report.ok ? 'success' : 'error'"
          variant="tonal"
          :title="report.ok ? 'The test passed' : 'The test failed'"
          class="mb-6"
          data-test="report"
        >
          <ul class="integration__checks">
            <li v-for="check in report.checks" :key="check.connection" data-test="check">
              <strong v-if="report.checks.length > 1"
                >{{ connectionLabels(integration)[check.connection] }}:</strong
              >
              {{ check.message }}
            </li>
          </ul>
        </v-alert>
        <v-alert v-if="failure" type="error" variant="tonal" class="mb-6" data-test="failure">
          {{ failure }}
        </v-alert>

        <div class="integration__actions">
          <v-btn
            type="submit"
            color="primary"
            :prepend-icon="Plug"
            :loading="busy === 'saving' || busy === 'testing'"
            :disabled="busy === 'disconnecting'"
            data-test="save"
          >
            {{ connected ? 'Save and test' : 'Connect' }}
          </v-btn>
          <v-btn
            v-if="connected"
            variant="tonal"
            :prepend-icon="FlaskConical"
            :disabled="busy !== null || changed"
            data-test="test"
            @click="test"
          >
            Test connection
          </v-btn>
          <v-spacer />
          <v-btn
            v-if="connected"
            ref="disconnectButton"
            variant="text"
            color="error"
            :prepend-icon="Unplug"
            :disabled="busy !== null"
            data-test="disconnect"
            @click="confirming = true"
          >
            Disconnect
          </v-btn>
        </div>
        <p
          v-if="connected && changed"
          class="text-body-medium text-medium-emphasis mt-2"
          data-test="unsaved"
        >
          You have changes that aren't saved. Save and test applies them.
        </p>
      </form>

      <div v-if="confirming" ref="confirmation" tabindex="-1" class="mt-6" data-test="confirmation">
        <v-alert type="warning" variant="tonal" :title="`Disconnect ${integration.name}?`">
          <p class="mb-3">
            AresGate forgets the addresses, settings and keys it has for {{ integration.name }}.
            Nothing changes on {{ integration.name }} itself, and you can connect it again later.
          </p>
          <div class="d-flex flex-wrap ga-3">
            <v-btn
              color="error"
              :loading="busy === 'disconnecting'"
              data-test="confirm-disconnect"
              @click="disconnect(integration)"
            >
              Disconnect
            </v-btn>
            <v-btn
              variant="text"
              :disabled="busy === 'disconnecting'"
              data-test="cancel-disconnect"
              @click="cancelDisconnect"
            >
              Cancel
            </v-btn>
          </div>
        </v-alert>
      </div>

      <ApiLog
        :integration="integration.key"
        :connections="logConnections(integration)"
        :refresh="requests"
        class="mt-8"
      />
    </template>
  </v-container>
</template>

<style scoped>
.integration__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.integration__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 3.75rem;
  height: 3.75rem;
  border-radius: 16px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.integration__intro {
  flex: 1 1 18rem;
  min-width: 0;
}

.integration__intro h1,
.integration__intro p {
  margin: 0;
}

.integration__intro p {
  margin-top: 0.25rem;
}

.integration__steps {
  margin: 0;
  padding-left: 1.25rem;
}

.integration__steps li + li {
  margin-top: 0.75rem;
}

.integration__checks {
  margin: 0;
  padding-left: 1rem;
}

.integration__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
