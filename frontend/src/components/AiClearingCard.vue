<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

import {
  CLEARING_CEILINGS,
  CLEARING_KINDS,
  CLEARING_MODES,
  fetchClearing,
  previewClearing,
  saveClearing,
  type Clearing,
  type ClearingDraft,
  type ClearingKind,
  type ClearingPreview,
} from '@/api/aiClearing'
import { errorMessage } from '@/api/client'
import {
  CEILING_WORDS,
  KIND_WORDS,
  MODE_WORDS,
  draftOf,
  previewSentence,
  sameDraft,
} from '@/aiClearing'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > AI > Clearing: whether the AI may clear what it reads as a false positive, and on
 * what terms. The card keeps a draft beside what is kept, asks the server what the draft would
 * have done to the incidents the AI read in the last 7 days a moment after the last change (so
 * dragging the slider is one question), and saves all of it at once. The AI never clears an
 * attack, a compromise or a critical incident, whatever is set here.
 */
const PAUSE = 400

const session = useSessionStore()
const modeId = useId()
const kindsId = useId()
const sourcesId = useId()
const ceilingId = useId()

const kept = ref<Clearing | null>(null)
const draft = ref<ClearingDraft | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const preview = ref<ClearingPreview | null>(null)
const working = ref(false)
const previewFailure = ref<string | null>(null)
const saving = ref(false)
const saveFailure = ref<string | null>(null)
const saved = ref(false)

let timer: ReturnType<typeof setTimeout> | undefined
// Which question is the latest, so an answer to an older one is dropped.
let asked = 0

// Read only once both are loaded: the draft is made from what is kept.
const changed = computed(
  () => !sameDraft(draft.value as ClearingDraft, draftOf(kept.value as Clearing)),
)
const automatic = computed(() => draft.value?.mode === 'automatic')
const aggressiveness = computed(
  () =>
    kept.value?.presets.find((preset) => preset.minimum === draft.value?.minimum)?.key ?? 'custom',
)
const summary = computed(
  () => kept.value?.presets.find((preset) => preset.key === aggressiveness.value)?.summary,
)
const sentence = computed(() => (preview.value ? previewSentence(preview.value) : ''))
const noKinds = computed(() => draft.value?.kinds.length === 0)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(fetchClearing)
    kept.value = found
    draft.value = draftOf(found)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function ask() {
  const question = ++asked
  const wanted = draft.value as ClearingDraft
  previewFailure.value = null
  try {
    const answer = await session.change((token) => previewClearing(wanted, token))
    if (question === asked) preview.value = answer
  } catch (error) {
    if (question === asked) {
      preview.value = null
      previewFailure.value = errorMessage(error)
    }
  } finally {
    if (question === asked) working.value = false
  }
}

// What the card says that differs from what is kept is worked out a moment after the last change,
// and withdraws the note that it was saved. Saying what is kept again (by going back, or by saving)
// withdraws the question and its answer.
watch(
  draft,
  () => {
    clearTimeout(timer)
    if (!changed.value) {
      asked++
      preview.value = null
      previewFailure.value = null
      working.value = false
      return
    }
    saved.value = false
    working.value = true
    timer = setTimeout(ask, PAUSE)
  },
  { deep: true },
)

function discard() {
  draft.value = draftOf(kept.value as Clearing)
}

/** A preset was chosen: how sure the AI must be becomes what it asks. */
function care(key: string) {
  const preset = kept.value?.presets.find((item) => item.key === key)
  if (preset && draft.value) draft.value.minimum = preset.minimum
}

/** What is wrong with the most it may clear in a day, or nothing. */
function capProblem(value: number): string | true {
  const most = (kept.value as Clearing).max_cap
  return (
    (Number.isInteger(value) && value >= 0 && value <= most) ||
    `Use a whole number from 0 to ${most.toString()}.`
  )
}

function toggleKind(kind: ClearingKind, on: boolean) {
  const wanted = draft.value as ClearingDraft
  wanted.kinds = CLEARING_KINDS.filter((item) => (item === kind ? on : wanted.kinds.includes(item)))
}

async function save() {
  const wanted = draft.value as ClearingDraft
  saving.value = true
  saveFailure.value = null
  try {
    const keptNow = await session.change((token) => saveClearing(wanted, token))
    kept.value = keptNow
    // The draft is what was saved, whatever else has changed on the card since.
    draft.value = draftOf(keptNow)
    saved.value = true
  } catch (error) {
    saveFailure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

const spoken = ({ value }: { value: number }) => `${value.toString()} percent sure`

onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(timer)
})
</script>

<template>
  <SectionCard
    title="Clearing"
    description="Whether the AI may clear what it reads as a false positive, and on what terms. It never clears an attack, a compromise or a critical incident, whatever is set here."
    data-test="clearing-card"
  >
    <LoadError
      v-if="loadError && !kept"
      :message="loadError"
      :loading="loading"
      data-test="clearing-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!kept || !draft" type="paragraph, paragraph" />
    <form v-else class="clearing" novalidate @submit.prevent="save">
      <fieldset class="clearing__group">
        <legend :id="modeId" class="text-title-small">What it does</legend>
        <v-radio-group
          v-model="draft.mode"
          hide-details
          :aria-labelledby="modeId"
          data-test="clearing-mode"
        >
          <v-radio
            v-for="mode in CLEARING_MODES"
            :key="mode"
            :value="mode"
            color="primary"
            :data-test="`clearing-mode-${mode}`"
          >
            <template #label>
              <span class="clearing__choice">
                <span class="text-body-large">{{ MODE_WORDS[mode].title }}</span>
                <span class="text-body-medium text-medium-emphasis">
                  {{ MODE_WORDS[mode].words }}
                </span>
              </span>
            </template>
          </v-radio>
        </v-radio-group>
      </fieldset>

      <v-alert
        v-if="kept.held"
        type="warning"
        variant="tonal"
        density="comfortable"
        data-test="clearing-held"
      >
        {{ kept.held }}
      </v-alert>
      <p
        v-if="kept.mode === 'automatic' && !kept.held"
        class="text-body-medium text-medium-emphasis"
        data-test="clearing-today"
      >
        Cleared by the AI in the last 24 hours: {{ kept.cleared_today }} of {{ kept.daily_cap }}.
      </p>

      <template v-if="draft.mode !== 'off'">
        <div class="clearing__group" data-test="clearing-sure">
          <h3 class="text-title-small">How sure it must be</h3>
          <v-btn-toggle
            :model-value="aggressiveness"
            mandatory
            divided
            variant="outlined"
            color="primary"
            density="comfortable"
            aria-label="How careful the AI is"
            data-test="clearing-presets"
            @update:model-value="care(String($event))"
          >
            <v-btn
              v-for="preset in kept.presets"
              :key="preset.key"
              :value="preset.key"
              :data-test="`clearing-preset-${preset.key}`"
            >
              {{ preset.key }}
            </v-btn>
          </v-btn-toggle>
          <p class="text-body-medium" data-test="clearing-preset-words">
            {{
              summary ??
              'A number of your own. The AI clears only what it says it is at least this sure of.'
            }}
          </p>
          <div class="clearing__slider">
            <span class="text-title-medium" data-test="clearing-minimum">
              {{ draft.minimum }}% sure
            </span>
            <v-slider
              v-model="draft.minimum"
              :min="kept.min_minimum"
              :max="kept.max_minimum"
              :step="1"
              color="primary"
              hide-details
              name="How sure the AI has to be to clear an incident"
              :value-format="spoken"
              data-test="clearing-slider"
            />
          </div>
        </div>

        <fieldset class="clearing__group" data-test="clearing-kinds">
          <legend :id="kindsId" class="text-title-small">What it may clear</legend>
          <p class="text-body-medium text-medium-emphasis">Never an attack or a compromise.</p>
          <v-checkbox
            v-for="kind in CLEARING_KINDS"
            :key="kind"
            :model-value="draft.kinds.includes(kind)"
            color="primary"
            hide-details
            density="comfortable"
            :data-test="`clearing-kind-${kind}`"
            @update:model-value="toggleKind(kind, Boolean($event))"
          >
            <template #label>
              <span class="clearing__choice">
                <span class="text-body-large">{{ KIND_WORDS[kind].title }}</span>
                <span class="text-body-medium text-medium-emphasis">
                  {{ KIND_WORDS[kind].words }}
                </span>
              </span>
            </template>
          </v-checkbox>
          <p v-if="noKinds" class="text-body-medium" data-test="clearing-no-kinds">
            With none chosen the AI clears nothing.
          </p>
        </fieldset>

        <div class="clearing__group">
          <h3 :id="sourcesId" class="text-title-small">Whose incidents</h3>
          <v-select
            v-model="draft.sources"
            :items="kept.available_sources"
            item-title="name"
            item-value="key"
            multiple
            chips
            closable-chips
            clearable
            label="Programs"
            placeholder="Any program"
            persistent-placeholder
            hint="Leave empty for any program. Name some to limit it to incidents that involve only those."
            persistent-hint
            :aria-labelledby="sourcesId"
            data-test="clearing-sources"
          />
        </div>

        <div class="clearing__group">
          <h3 :id="ceilingId" class="text-title-small">How serious</h3>
          <v-btn-toggle
            v-model="draft.ceiling"
            mandatory
            divided
            variant="outlined"
            color="primary"
            density="comfortable"
            :aria-labelledby="ceilingId"
            data-test="clearing-ceilings"
          >
            <v-btn
              v-for="ceiling in CLEARING_CEILINGS"
              :key="ceiling"
              :value="ceiling"
              :data-test="`clearing-ceiling-${ceiling}`"
            >
              {{ ceiling }}
            </v-btn>
          </v-btn-toggle>
          <p class="text-body-medium" data-test="clearing-ceiling-words">
            {{ CEILING_WORDS[draft.ceiling] }}
          </p>
        </div>

        <div v-if="automatic" class="clearing__group">
          <v-text-field
            v-model.number="draft.daily_cap"
            type="number"
            inputmode="numeric"
            label="Most it clears a day"
            :min="0"
            :max="kept.max_cap"
            :rules="[capProblem]"
            hint="In any 24 hours. Past it, what the AI finds waits for you. 0 clears nothing by itself."
            persistent-hint
            data-test="clearing-cap"
          />
        </div>
      </template>

      <div class="clearing__effect" aria-live="polite">
        <v-progress-linear
          v-if="working"
          indeterminate
          aria-label="Working out what this would have cleared"
        />
        <output v-if="sentence && !working" class="text-body-large" data-test="clearing-preview">
          {{ sentence }}
        </output>
        <p
          v-if="previewFailure"
          class="text-body-medium text-error"
          role="alert"
          data-test="clearing-preview-error"
        >
          {{ previewFailure }}
        </p>
      </div>

      <v-alert
        v-if="saveFailure"
        type="error"
        variant="tonal"
        density="comfortable"
        data-test="clearing-failure"
      >
        {{ saveFailure }}
      </v-alert>
      <p
        v-if="saved && !changed"
        class="text-body-medium text-success"
        role="status"
        data-test="clearing-saved"
      >
        The settings are saved.
      </p>

      <div class="clearing__actions">
        <v-btn
          variant="text"
          :disabled="!changed || saving"
          data-test="clearing-discard"
          @click="discard"
        >
          Discard changes
        </v-btn>
        <v-btn
          type="submit"
          color="primary"
          variant="flat"
          :disabled="!changed"
          :loading="saving"
          data-test="clearing-save"
        >
          Save
        </v-btn>
      </div>
    </form>
  </SectionCard>
</template>

<style scoped>
.clearing {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.clearing__group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.clearing__group h3,
.clearing__group legend,
.clearing p {
  margin: 0;
}

.clearing__choice {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}

.clearing__slider {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.clearing__effect {
  min-height: 1.5rem;
}

.clearing__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
