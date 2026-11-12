<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  REVIEW_MODES,
  fetchReviewSettings,
  saveReviewSettings,
  type ReviewDraft,
  type ReviewSettings,
} from '@/api/review'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { REVIEW_MODE, autoFromSentence } from '@/review'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > Review: how much of what the AI decides waits for the owner. The AI may always sound
 * an alarm on its own. What it would set aside waits for them (the default), or only the part it
 * is unsure of does, or none of it. Whatever is chosen, the decisions are listed on the Review
 * page and can be disagreed with, and the AI learns from what is said.
 */
const session = useSessionStore()

const kept = ref<ReviewSettings | null>(null)
const draft = ref<ReviewDraft | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)
const failure = ref<string | null>(null)

const changed = computed(() => {
  const was = kept.value as ReviewSettings
  const now = draft.value as ReviewDraft
  return was.mode !== now.mode || was.auto_from !== now.auto_from || was.learn !== now.learn
})
const spoken = ({ value }: { value: number }) => `${value.toString()} percent sure`

function draftOf(settings: ReviewSettings): ReviewDraft {
  return { mode: settings.mode, auto_from: settings.auto_from, learn: settings.learn }
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(fetchReviewSettings)
    kept.value = found
    draft.value = draftOf(found)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function save() {
  const wanted = draft.value as ReviewDraft
  saving.value = true
  failure.value = null
  try {
    const found = await session.change((token) => saveReviewSettings(wanted, token))
    kept.value = found
    draft.value = draftOf(found)
    saved.value = true
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

function discard() {
  draft.value = draftOf(kept.value as ReviewSettings)
  saved.value = false
}

onMounted(load)
</script>

<template>
  <LoadError
    v-if="loadError && !kept"
    :message="loadError"
    :loading="loading"
    data-test="review-settings-error"
    @retry="load"
  />
  <v-skeleton-loader
    v-else-if="!kept || !draft"
    type="card, card"
    data-test="review-settings-loading"
  />
  <template v-else>
    <SectionCard
      title="How much waits for you"
      description="The AI may always raise an alarm on its own. This is about what it would set aside, as harmless or as a probe."
      data-test="review-mode-card"
    >
      <v-radio-group
        v-model="draft.mode"
        hide-details
        color="primary"
        aria-label="How much of what the AI decides waits for you"
        data-test="review-mode"
        @update:model-value="saved = false"
      >
        <v-radio
          v-for="mode in REVIEW_MODES"
          :key="mode"
          :value="mode"
          :data-test="`review-mode-${mode}`"
        >
          <template #label>
            <span class="mode">
              <span class="text-title-medium">{{ REVIEW_MODE[mode].label }}</span>
              <span class="text-body-medium text-medium-emphasis">
                {{ REVIEW_MODE[mode].meaning }}
              </span>
            </span>
          </template>
        </v-radio>
      </v-radio-group>

      <div v-if="draft.mode === 'uncertain'" class="bar" data-test="review-from-bar">
        <div class="bar__head">
          <span class="text-title-medium" data-test="review-from-value">
            {{ draft.auto_from }}% sure
          </span>
          <v-btn
            v-if="draft.auto_from !== kept.default_auto_from"
            variant="text"
            size="small"
            data-test="review-from-reset"
            @click="draft.auto_from = kept.default_auto_from"
          >
            Back to {{ kept.default_auto_from }}
          </v-btn>
        </div>
        <v-slider
          v-model="draft.auto_from"
          :min="kept.min_auto_from"
          :max="100"
          :step="1"
          color="primary"
          hide-details
          name="How sure the AI has to be for a decision to count at once"
          :value-format="spoken"
          data-test="review-from-slider"
          @update:model-value="saved = false"
        />
        <p class="text-body-large" data-test="review-from-sentence">
          {{ autoFromSentence(draft.auto_from) }}
        </p>
      </div>
    </SectionCard>

    <SectionCard
      title="What the AI learns"
      description="It decides better when it knows where it was wrong."
      data-test="review-learn-card"
    >
      <v-switch
        v-model="draft.learn"
        label="Tell the AI what I disagreed with, and why"
        color="primary"
        density="comfortable"
        hide-details
        data-test="review-learn"
        @update:model-value="saved = false"
      />
      <p class="learn text-body-medium text-medium-emphasis">
        The last few decisions you disagreed with, and your reasons, are added to what the AI is
        asked the next time it reads an incident or judges a kind. Addresses in them are hidden from
        a hosted AI as they are everywhere else.
      </p>
    </SectionCard>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      role="alert"
      data-test="review-save-failure"
    >
      {{ failure }}
    </v-alert>
    <div class="actions">
      <v-btn
        color="primary"
        :loading="saving"
        :disabled="!changed || saving"
        data-test="review-save"
        @click="save"
      >
        Save
      </v-btn>
      <v-btn
        variant="text"
        :disabled="!changed || saving"
        data-test="review-discard"
        @click="discard"
      >
        Discard changes
      </v-btn>
      <output v-if="saved && !changed" class="text-body-large" data-test="review-saved"
        >Saved.</output
      >
    </div>
    <p class="text-body-medium text-medium-emphasis">
      A decision the AI made before counts as it did. A new setting applies to what it decides from
      now on.
    </p>
  </template>
</template>

<style scoped>
.mode {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0;
}

.bar {
  margin: 1rem 0 0;
  padding-inline-start: 2.5rem;
}

.bar p {
  margin: 0.75rem 0 0;
}

.bar__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.25rem;
}

.learn {
  margin: 0.25rem 0 0;
  padding-inline-start: 3.5rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
</style>
