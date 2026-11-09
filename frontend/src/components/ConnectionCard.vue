<script setup lang="ts">
import { ShieldAlert, TriangleAlert } from '@lucide/vue'
import { computed, nextTick, ref } from 'vue'

import type { Connection } from '@/api/integrations'
import LookupField from '@/components/LookupField.vue'
import ModuleList from '@/components/ModuleList.vue'
import SecretField from '@/components/SecretField.vue'
import SectionCard from '@/components/SectionCard.vue'
import StatusChip from '@/components/StatusChip.vue'
import TlsSettings from '@/components/TlsSettings.vue'
import { formatAgo, formatDateTime } from '@/format'
import {
  WHOLE,
  activeFields,
  fieldId,
  isPlainHttp,
  usesTls,
  type ConnectionDraft,
} from '@/integrations'

/**
 * One connection of an integration: where it is, how to sign in to it and how to check its
 * certificate, each as its definition says. OPNsense has two (its own API, and Zenarmor's, which
 * not everyone has), Wazuh has two, and the others have one.
 */
const props = defineProps<{
  /** The integration's key. */
  integration: string
  connection: Connection
  /** What is wrong with each field, as the API said: by field name, or under `connection` for
   * the connection as a whole. */
  problems: Readonly<Record<string, string>>
  /** Counts the tests that have been run. A field that lists what the system has asks it again
   * after a test that passed, so the list matches what the test found. A failed test may have been
   * a refused login, which would only be refused again. */
  refresh?: number
}>()
const draft = defineModel<ConnectionDraft>({ required: true })
const emit = defineEmits<{
  /** A field asked the system for its choices, which is a request the log of requests has. */
  asked: []
  /** A certificate was trusted, and whether to save and test the connection straight after. */
  trusted: [test: boolean]
}>()

const tls = ref<{ review: () => Promise<void> } | null>(null)

const definition = computed(() => props.connection.definition)
const saved = computed(() => props.connection.url !== null)
/** Changes after each test that passed, which is when a field that lists asks again. */
const listAgain = computed(() =>
  props.connection.status === 'connected' ? props.refresh : undefined,
)
const fields = computed(() => activeFields(definition.value, draft.value.options))
const id = (field: string) => fieldId(definition.value.key, field)
const urlHint = computed(() =>
  definition.value.allow_http
    ? 'Where it listens, with http:// or https:// and the port.'
    : 'Where it listens, with https:// and the port.',
)

function secret(key: string): string {
  return draft.value.secrets[key] ?? ''
}

/** Whether the last failure is one that looking at the certificate may cure. */
const reviewable = computed(() => props.connection.certificate_problem && usesTls(draft.value.url))

/** Looks up the certificate the system presents and shows it, for a button elsewhere on the page
 * (a failed test says what is wrong with it and offers this). */
async function reviewCertificate() {
  await nextTick()
  await tls.value?.review()
}
defineExpose({ reviewCertificate })
</script>

<template>
  <SectionCard
    :title="definition.label"
    :description="definition.summary"
    :data-test="`connection-${definition.key}`"
  >
    <template v-if="saved" #actions>
      <StatusChip :status="connection.status" data-test="connection-status" />
    </template>

    <template v-if="definition.optional">
      <v-switch
        v-model="draft.enabled"
        :label="`Use ${definition.label}`"
        color="primary"
        inset
        hide-details
        data-test="connection-enabled"
      />
      <p
        v-if="saved && !draft.enabled"
        class="text-body-medium text-medium-emphasis mt-1"
        data-test="connection-forget"
      >
        Saving forgets its address and key.
      </p>
    </template>

    <div v-if="draft.enabled" class="connection__body">
      <v-alert
        v-if="problems[WHOLE]"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-4"
        data-test="connection-problem"
      >
        {{ problems[WHOLE] }}
      </v-alert>
      <v-alert
        v-if="connection.last_error"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-4"
        title="The last test failed"
        data-test="connection-last-error"
      >
        {{ connection.last_error }}
        <div v-if="reviewable" class="mt-3">
          <v-btn
            color="primary"
            :prepend-icon="ShieldAlert"
            data-test="connection-review-certificate"
            @click="reviewCertificate"
          >
            Review the certificate
          </v-btn>
        </div>
      </v-alert>
      <p
        v-else-if="connection.last_success_at"
        class="text-body-medium text-medium-emphasis mb-4"
        data-test="connection-last-success"
      >
        Last successful call
        <time
          :datetime="connection.last_success_at"
          :title="formatDateTime(connection.last_success_at)"
          >{{ formatAgo(connection.last_success_at) }}</time
        >
      </p>

      <v-text-field
        v-if="definition.address"
        :id="id('url')"
        :model-value="definition.address"
        label="Address"
        readonly
        hint="This service has one address, so AresGate only ever sends its key there."
        persistent-hint
        data-test="connection-url"
      />
      <v-text-field
        v-else
        :id="id('url')"
        v-model="draft.url"
        label="Address"
        :placeholder="definition.url_example"
        :hint="urlHint"
        persistent-hint
        inputmode="url"
        autocomplete="off"
        spellcheck="false"
        autocapitalize="off"
        :error-messages="problems.url"
        data-test="connection-url"
      />
      <v-alert
        v-if="isPlainHttp(draft.url)"
        type="warning"
        variant="tonal"
        density="compact"
        :icon="TriangleAlert"
        class="mt-4"
        data-test="connection-plain-http"
      >
        This address uses http, so what AresGate signs in with is sent without encryption and anyone
        on your network could read it. Use https if it can.
      </v-alert>

      <div class="connection__fields">
        <template v-for="field in fields" :key="field.key">
          <SecretField
            v-if="field.kind === 'secret'"
            :id="id(field.key)"
            :model-value="secret(field.key)"
            :label="field.label"
            :saved="connection.secrets_set.includes(field.key)"
            :hint="field.help || undefined"
            :error-messages="problems[field.key]"
            :data-test="`field-${field.key}`"
            @update:model-value="draft.secrets[field.key] = $event"
          />
          <LookupField
            v-else-if="field.kind === 'lookup'"
            :id="id(field.key)"
            v-model="draft.options[field.key]!"
            :integration="integration"
            :definition="definition"
            :field="field"
            :draft="draft"
            :saved="saved"
            :refresh="listAgain"
            :error-messages="problems[field.key]"
            @asked="emit('asked')"
          />
          <v-radio-group
            v-else-if="field.kind === 'choice'"
            v-model="draft.options[field.key]"
            :label="field.label"
            :error-messages="problems[field.key]"
            hide-details="auto"
            :data-test="`field-${field.key}`"
          >
            <v-radio
              v-for="choice in field.choices"
              :key="choice.value"
              :value="choice.value"
              :label="choice.label"
            />
          </v-radio-group>
          <v-text-field
            v-else
            :id="id(field.key)"
            v-model="draft.options[field.key]"
            :label="field.label"
            :placeholder="field.placeholder || undefined"
            :hint="field.help || undefined"
            :persistent-hint="field.help !== ''"
            :type="field.kind === 'number' ? 'number' : 'text'"
            :min="field.kind === 'number' ? field.minimum : undefined"
            :max="field.kind === 'number' ? field.maximum : undefined"
            :inputmode="field.kind === 'number' ? 'numeric' : undefined"
            autocomplete="off"
            spellcheck="false"
            :error-messages="problems[field.key]"
            :data-test="`field-${field.key}`"
          />
          <v-alert
            v-if="field.caution"
            type="warning"
            variant="tonal"
            density="compact"
            :icon="TriangleAlert"
            class="mt-2"
            :data-test="`caution-${field.key}`"
          >
            {{ field.caution }}
          </v-alert>
        </template>
      </div>

      <TlsSettings
        v-if="usesTls(draft.url)"
        ref="tls"
        v-model:mode="draft.tlsMode"
        v-model:authority="draft.tlsCaPem"
        v-model:fingerprint="draft.tlsFingerprint"
        :integration="integration"
        :url="draft.url"
        :id-prefix="definition.key"
        :problems="problems"
        :note="definition.certificate_note"
        :can-test="saved"
        class="connection__section"
        @trusted="emit('trusted', $event)"
      />

      <ModuleList
        v-if="connection.modules.length"
        v-model="draft.disabledModules"
        :modules="connection.modules"
        :id-prefix="definition.key"
        class="connection__section"
      />
    </div>
  </SectionCard>
</template>

<style scoped>
.connection__body {
  margin-top: 1rem;
}

.connection__fields {
  display: grid;
  gap: 1rem;
  margin-top: 1rem;
}

.connection__section {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}
</style>
