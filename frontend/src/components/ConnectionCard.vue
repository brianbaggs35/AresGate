<script setup lang="ts">
import { TriangleAlert } from '@lucide/vue'
import { computed } from 'vue'

import type { Connection } from '@/api/integrations'
import ModuleList from '@/components/ModuleList.vue'
import SecretField from '@/components/SecretField.vue'
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
}>()
const draft = defineModel<ConnectionDraft>({ required: true })

const definition = computed(() => props.connection.definition)
const saved = computed(() => props.connection.url !== null)
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
</script>

<template>
  <v-card class="pa-6" :data-test="`connection-${definition.key}`">
    <div class="connection__head">
      <div class="connection__title">
        <h2 class="text-title-large">{{ definition.label }}</h2>
        <p class="text-body-medium text-medium-emphasis" data-test="connection-summary">
          {{ definition.summary }}
        </p>
      </div>
      <StatusChip v-if="saved" :status="connection.status" data-test="connection-status" />
    </div>

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
        </template>
      </div>

      <TlsSettings
        v-if="usesTls(draft.url)"
        v-model:mode="draft.tlsMode"
        v-model:authority="draft.tlsCaPem"
        v-model:fingerprint="draft.tlsFingerprint"
        :integration="integration"
        :url="draft.url"
        :id-prefix="definition.key"
        :problems="problems"
        class="connection__section"
      />

      <ModuleList
        v-if="connection.modules.length"
        v-model="draft.disabledModules"
        :modules="connection.modules"
        :id-prefix="definition.key"
        class="connection__section"
      />
    </div>
  </v-card>
</template>

<style scoped>
.connection__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 0.5rem;
}

.connection__title {
  flex: 1 1 16rem;
  min-width: 0;
}

.connection__title p {
  margin: 0;
}

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
