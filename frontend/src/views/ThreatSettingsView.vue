<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchThreatSettings,
  previewThreatSettings,
  saveThreatSettings,
  type ThreatDraft,
  type ThreatPreview,
  type ThreatSettings,
} from '@/api/threatSettings'
import LoadError from '@/components/LoadError.vue'
import ThreatAiCard from '@/components/ThreatAiCard.vue'
import ThreatEffect from '@/components/ThreatEffect.vue'
import ThreatLevelCard from '@/components/ThreatLevelCard.vue'
import ThreatNetworkCard from '@/components/ThreatNetworkCard.vue'
import { useSessionStore } from '@/stores/session'
import { draftOf, sameDraft } from '@/threats'

/**
 * Settings > Threat detection: how AresGate tells a threat from background on your network. The
 * page keeps a draft beside what is kept, asks the server what the draft would do as soon as it
 * differs (a moment after the last change, so dragging a slider is one question), and saves all of
 * it at once.
 */
const PAUSE = 400

const session = useSessionStore()

const kept = ref<ThreatSettings | null>(null)
const draft = ref<ThreatDraft | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const preview = ref<ThreatPreview | null>(null)
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
  () => !sameDraft(draft.value as ThreatDraft, draftOf(kept.value as ThreatSettings)),
)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(fetchThreatSettings)
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
  const wanted = draft.value as ThreatDraft
  working.value = true
  previewFailure.value = null
  try {
    const answer = await session.change((token) => previewThreatSettings(wanted, token))
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

// Whatever the page says that differs from what is kept is worked out a moment after the last
// change, and withdraws the note that it was saved. Saying what is kept again (by going back, or
// by saving) withdraws the question and its answer.
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
  draft.value = draftOf(kept.value as ThreatSettings)
}

async function save() {
  const wanted = draft.value as ThreatDraft
  saving.value = true
  saveFailure.value = null
  try {
    const keptNow = await session.change((token) => saveThreatSettings(wanted, token))
    kept.value = keptNow
    // The draft is what was saved, whatever else has changed on the page since.
    draft.value = draftOf(keptNow)
    saved.value = true
  } catch (error) {
    saveFailure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(timer)
})
</script>

<template>
  <LoadError
    v-if="loadError && !kept"
    :message="loadError"
    :loading="loading"
    data-test="threat-settings-error"
    @retry="load"
  />
  <v-skeleton-loader
    v-else-if="!kept || !draft"
    type="card, card"
    data-test="threat-settings-loading"
  />
  <template v-else>
    <ThreatLevelCard v-model="draft.threat_from" :default-value="kept.default_threat_from" />
    <ThreatAiCard
      v-model:may-clear="draft.ai_may_clear"
      v-model:clear-from="draft.clear_from"
      v-model:confirms="draft.ai_confirms"
      :default-clear-from="kept.default_clear_from"
      :min-clear-from="kept.min_clear_from"
      :watching="kept.watching"
    />
    <ThreatNetworkCard
      v-model:exposure="draft.exposure"
      v-model:ports="draft.exposed_ports"
      v-model:notes="draft.notes"
      :max-ports="kept.max_ports"
      :max-notes="kept.max_notes"
    />
    <ThreatEffect
      :preview="preview"
      :changed="changed"
      :loading="working"
      :saving="saving"
      :failure="saveFailure ?? previewFailure"
      :saved="saved"
      @save="save"
      @discard="discard"
    />
  </template>
</template>
