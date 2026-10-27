<script setup lang="ts">
import {
  CircleCheck,
  ExternalLink,
  FlaskConical,
  ListRestart,
  Save,
  Trash2,
  TriangleAlert,
} from '@lucide/vue'
import { computed, reactive, ref } from 'vue'

import {
  fetchProviderModels,
  removeProvider,
  saveProvider,
  testProvider,
  type AiCheck,
  type AiProvider,
} from '@/api/ai'
import { ApiError, errorMessage } from '@/api/client'
import {
  FIELD_ORDER,
  cachingNote,
  canTest,
  describePrice,
  draftFrom,
  estimateNote,
  foundItems,
  isChanged,
  longPromptNote,
  modelItems,
  problemsByField,
  providerFieldId,
  settingsFrom,
} from '@/ai'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SecretField from '@/components/SecretField.vue'
import SectionCard from '@/components/SectionCard.vue'
import StatusChip from '@/components/StatusChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * One AI provider: how to reach it, which model to ask, and buttons to test it. A hosted
 * provider (Anthropic, OpenAI) takes an API key and one model of a list that comes with its
 * prices. An Ollama on the owner's computer takes an address, and Ollama's cloud a key; both
 * have whatever models they have, which a button asks for. Testing or asking for models saves
 * what was filled in first, so what is tested is what is kept.
 */
const props = defineProps<{ provider: AiProvider; pricedAsOf: string }>()
const emit = defineEmits<{ changed: [provider: AiProvider]; removed: [key: string] }>()

const session = useSessionStore()

const draft = reactive(draftFrom(props.provider))
const problems = ref<Record<string, string>>({})
const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const working = ref<'save' | 'test' | 'models' | 'remove' | null>(null)
const confirming = ref(false)

const id = (field: string) => providerFieldId(props.provider.key, field)
const hosted = computed(() => props.provider.kind === 'hosted')
const chosen = computed(() => props.provider.models.find((model) => model.id === draft.model))
const testable = computed(() => canTest(props.provider, draft))
const askable = computed(() => !hosted.value && testable.value)
const lookedUp = computed(() => props.provider.found.length)
const host = (url: string) => new URL(url).hostname

function begin(kind: 'save' | 'test' | 'models' | 'remove') {
  working.value = kind
  notice.value = null
  failure.value = null
  problems.value = {}
}

function focusProblem() {
  const field = FIELD_ORDER.find((name) => name in problems.value)
  if (field) document.getElementById(id(field))?.focus()
}

/** Keeps what was filled in. Returns what is kept, or nothing after showing what was wrong. */
async function persist(): Promise<AiProvider | undefined> {
  try {
    const saved = await session.change((token) =>
      saveProvider(props.provider.key, settingsFrom(props.provider, draft), token),
    )
    Object.assign(draft, draftFrom(saved))
    emit('changed', saved)
    return saved
  } catch (error) {
    if (error instanceof ApiError && error.problems.length > 0) {
      problems.value = problemsByField(error.problems)
      // The page has to have shown the problem before the keyboard can be put on it.
      queueMicrotask(focusProblem)
    } else {
      failure.value = errorMessage(error)
    }
    return undefined
  }
}

async function save() {
  begin('save')
  try {
    if (await persist()) notice.value = 'Saved.'
  } finally {
    working.value = null
  }
}

async function check(
  kind: 'test' | 'models',
  ask: (key: string, token: string) => Promise<AiCheck>,
) {
  begin(kind)
  try {
    if (isChanged(props.provider, draft) && !(await persist())) return
    const report = await session.change((token) => ask(props.provider.key, token))
    emit('changed', report.provider)
    // A failure is shown as the provider's last error, which the answer carries.
    if (report.ok) notice.value = report.message
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    working.value = null
  }
}

const test = () => check('test', testProvider)
const fetchModels = () => check('models', fetchProviderModels)

async function forget() {
  begin('remove')
  try {
    await session.change((token) => removeProvider(props.provider.key, token))
    Object.assign(draft, { model: props.provider.default_model ?? '', baseUrl: '', apiKey: '' })
    confirming.value = false
    emit('removed', props.provider.key)
  } catch (error) {
    failure.value = errorMessage(error)
    confirming.value = false
  } finally {
    working.value = null
  }
}
</script>

<template>
  <SectionCard
    :title="provider.label"
    :description="provider.summary"
    :data-test="`provider-${provider.key}`"
  >
    <template v-if="provider.configured" #actions>
      <StatusChip :status="provider.status" data-test="provider-status" />
    </template>

    <v-alert
      v-if="provider.last_error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      title="The last test failed"
      data-test="provider-last-error"
    >
      {{ provider.last_error }}
    </v-alert>
    <p
      v-else-if="provider.last_success_at"
      class="text-body-medium text-medium-emphasis mb-4"
      data-test="provider-last-success"
    >
      Last worked
      <time
        :datetime="provider.last_success_at"
        :title="formatDateTime(provider.last_success_at)"
        >{{ formatAgo(provider.last_success_at) }}</time
      >
    </p>

    <form class="provider__form" novalidate @submit.prevent="save">
      <v-text-field
        v-if="provider.takes_url"
        :id="id('base_url')"
        v-model="draft.baseUrl"
        label="Address"
        placeholder="http://192.168.1.50:11434"
        hint="Where Ollama listens on your network, with http:// and the port. Not localhost: AresGate runs in a container, so that is the container itself, not your computer. Ollama listens only on its own computer until it is told otherwise (OLLAMA_HOST)."
        persistent-hint
        inputmode="url"
        autocomplete="off"
        spellcheck="false"
        autocapitalize="off"
        :error-messages="problems.base_url"
        data-test="provider-url"
      />

      <template v-if="provider.needs_key">
        <SecretField
          :id="id('api_key')"
          v-model="draft.apiKey"
          label="API key"
          :saved="provider.key_saved"
          :error-messages="problems.api_key"
          data-test="provider-key"
        />
        <p
          v-if="provider.key_url"
          class="text-body-medium text-medium-emphasis provider__make-key"
          data-test="provider-key-help"
        >
          Make one at
          <a :href="provider.key_url" target="_blank" rel="noopener noreferrer">
            {{ host(provider.key_url) }}<ExternalLink :size="14" aria-hidden="true" /></a
          >. It is kept encrypted and never shown again.
        </p>
      </template>

      <v-select
        v-if="hosted"
        :id="id('model')"
        v-model="draft.model"
        label="Model"
        :items="modelItems(provider)"
        :error-messages="problems.model"
        data-test="provider-model"
      />
      <v-combobox
        v-else
        :id="id('model')"
        v-model="draft.model"
        label="Model"
        :items="foundItems(provider)"
        :return-object="false"
        :hint="
          lookedUp > 0
            ? `${formatCount(lookedUp)} found ${lookedUp === 1 ? 'model' : 'models'}: choose one, or type a name.`
            : 'Fetch the models to choose from what it has, or type a name such as llama3.2:3b.'
        "
        persistent-hint
        autocomplete="off"
        spellcheck="false"
        autocapitalize="off"
        :error-messages="problems.model"
        data-test="provider-model"
      />

      <div v-if="chosen" class="provider__price" data-test="provider-price">
        <p class="text-body-large">{{ describePrice(chosen.price) }}.</p>
        <p
          v-if="cachingNote(chosen)"
          class="text-body-medium text-medium-emphasis"
          data-test="provider-caching"
        >
          {{ cachingNote(chosen) }}
        </p>
        <p v-if="longPromptNote(chosen.price)" class="text-body-medium text-medium-emphasis">
          {{ longPromptNote(chosen.price) }}
        </p>
        <p class="text-body-medium text-medium-emphasis" data-test="provider-estimate">
          {{ estimateNote(chosen) }}
        </p>
        <p
          v-if="chosen.deprecated"
          class="provider__deprecated text-body-medium"
          data-test="provider-deprecated"
        >
          <TriangleAlert :size="16" aria-hidden="true" />
          {{ provider.label }} lists this model as deprecated, so it will be retired. Choose another
          when you can.
        </p>
        <p v-if="provider.pricing_url" class="text-body-medium text-medium-emphasis">
          Prices from
          <a :href="provider.pricing_url" target="_blank" rel="noopener noreferrer">
            {{ host(provider.pricing_url) }}<ExternalLink :size="14" aria-hidden="true" />
          </a>
          as of {{ pricedAsOf }}.
        </p>
      </div>
      <p
        v-else-if="provider.kind === 'local'"
        class="text-body-medium text-medium-emphasis"
        data-test="provider-free"
      >
        It runs on your own computer, so it costs nothing to ask and nothing leaves your network.
      </p>
      <p
        v-else-if="provider.kind === 'cloud'"
        class="text-body-medium text-medium-emphasis"
        data-test="provider-unpriced"
      >
        Ollama's cloud isn't priced per token here, so AresGate counts the tokens it uses and shows
        no cost.
      </p>

      <v-alert
        v-if="failure"
        type="error"
        variant="tonal"
        density="compact"
        class="mt-4"
        data-test="provider-failure"
      >
        {{ failure }}
      </v-alert>
      <output v-if="notice" class="provider__notice text-body-large" data-test="provider-notice">
        <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
        {{ notice }}
      </output>

      <div class="provider__actions">
        <v-btn
          type="submit"
          color="primary"
          :prepend-icon="Save"
          :loading="working === 'save'"
          :disabled="working !== null && working !== 'save'"
          data-test="provider-save"
        >
          Save
        </v-btn>
        <v-btn
          variant="tonal"
          :prepend-icon="FlaskConical"
          :loading="working === 'test'"
          :disabled="!testable || (working !== null && working !== 'test')"
          data-test="provider-test"
          @click="test"
        >
          Test connection
        </v-btn>
        <v-btn
          v-if="!hosted"
          variant="tonal"
          :prepend-icon="ListRestart"
          :loading="working === 'models'"
          :disabled="!askable || (working !== null && working !== 'models')"
          data-test="provider-models-fetch"
          @click="fetchModels"
        >
          Fetch models
        </v-btn>
        <v-btn
          v-if="provider.configured"
          variant="text"
          color="error"
          :prepend-icon="Trash2"
          :disabled="working !== null"
          class="provider__remove"
          data-test="provider-remove"
          @click="confirming = true"
        >
          Remove
        </v-btn>
      </div>
    </form>

    <ConfirmDialog
      v-model="confirming"
      :title="`Remove ${provider.label}?`"
      confirm-label="Remove it"
      destructive
      :busy="working === 'remove'"
      @confirm="forget"
    >
      <p v-if="provider.needs_key">
        Its settings and its API key are deleted from AresGate. The key still works at the provider
        until you delete it there. If it is the one AresGate asks, AI is turned off.
      </p>
      <p v-else>
        Its settings are deleted from AresGate. If it is the one AresGate asks, AI is turned off.
      </p>
    </ConfirmDialog>
  </SectionCard>
</template>

<style scoped>
.provider__form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.provider__make-key {
  margin: -0.5rem 0 0;
}

.provider__make-key a,
.provider__price a {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}

.provider__price {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  border-radius: var(--v-border-radius, 8px);
  background: rgb(var(--v-theme-surface-variant), 0.35);
}

.provider__price p {
  margin: 0;
}

.provider__deprecated {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
}

.provider__deprecated svg {
  flex: none;
  margin-top: 0.15rem;
  color: rgb(var(--v-theme-warning));
}

.provider__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.provider__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

/* On a computer, Remove sits apart from the buttons that keep or test. */
@media (min-width: 600px) {
  .provider__remove {
    margin-inline-start: auto;
  }
}
</style>
