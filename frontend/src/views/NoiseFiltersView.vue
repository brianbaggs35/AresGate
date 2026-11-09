<script setup lang="ts">
import { Gavel } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchNoiseFilters,
  previewNoiseFilters,
  saveNoiseFilters,
  type NoiseDraft,
  type NoiseFilters,
  type Preview,
} from '@/api/noise'
import LoadError from '@/components/LoadError.vue'
import NoiseEffect from '@/components/NoiseEffect.vue'
import NoiseFloorCard from '@/components/NoiseFloorCard.vue'
import NoiseGapCard from '@/components/NoiseGapCard.vue'
import NoiseInsideCard from '@/components/NoiseInsideCard.vue'
import NoiseSourcesCard from '@/components/NoiseSourcesCard.vue'
import NoiseThinCard from '@/components/NoiseThinCard.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount } from '@/format'
import { draftOf, sameDraft, withFloor } from '@/noiseFilters'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > Noise filters: how AresGate narrows what it asks about without a verdict from you.
 * The page keeps a draft beside what is kept, asks the server what the draft would do as soon as
 * it differs (a moment after the last change, so dragging the slider is one question), and saves
 * all of it at once.
 */
const PAUSE = 400

const session = useSessionStore()

const kept = ref<NoiseFilters | null>(null)
const draft = ref<NoiseDraft | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const preview = ref<Preview | null>(null)
const working = ref(false)
const previewFailure = ref<string | null>(null)
const saving = ref(false)
const saveFailure = ref<string | null>(null)
const saved = ref(false)

let timer: ReturnType<typeof setTimeout> | undefined
// Which question is the latest, so an answer to an older one is dropped.
let asked = 0

const changed = computed(() =>
  kept.value && draft.value ? !sameDraft(draft.value, draftOf(kept.value)) : false,
)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(fetchNoiseFilters)
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
  const wanted = draft.value as NoiseDraft
  working.value = true
  previewFailure.value = null
  try {
    const answer = await session.change((token) => previewNoiseFilters(wanted, token))
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
  draft.value = draftOf(kept.value as NoiseFilters)
}

async function save() {
  const wanted = draft.value as NoiseDraft
  saving.value = true
  saveFailure.value = null
  try {
    const keptNow = await session.change((token) => saveNoiseFilters(wanted, token))
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
    data-test="noise-error"
    @retry="load"
  />
  <v-skeleton-loader v-else-if="!kept || !draft" type="card, card" data-test="noise-loading" />
  <template v-else>
    <NoiseFloorCard
      v-model="draft.confidence_floor"
      :default-floor="kept.default_floor"
      :medium-from="kept.medium_from"
      :high-from="kept.high_from"
    />
    <NoiseSourcesCard
      :sources="kept.sources"
      :floors="draft.source_floors"
      @change="(key, floor) => (draft = withFloor(draft as NoiseDraft, key, floor))"
    />
    <NoiseThinCard
      v-model="draft.thin_low_signals"
      :default-minimum="kept.default_thin_low_signals"
    />
    <NoiseInsideCard v-model="draft.quiet_inside" />
    <NoiseGapCard
      v-model:scan-hours="draft.scan_gap_hours"
      v-model:brute-force-hours="draft.brute_force_gap_hours"
      :default-scan-hours="kept.default_scan_gap_hours"
      :default-brute-force-hours="kept.default_brute_force_gap_hours"
    />
    <SectionCard
      title="Verdicts"
      description="Your own verdicts come first. What you called not suspicious or low priority is left out whatever these settings say, and a real threat is never set aside."
      data-test="verdicts-link-card"
    >
      <v-btn
        variant="tonal"
        :prepend-icon="Gavel"
        :to="{ name: 'settings-verdicts' }"
        data-test="manage-verdicts"
      >
        {{
          kept.verdicts === 1
            ? 'Manage your 1 verdict'
            : `Manage your ${formatCount(kept.verdicts)} verdicts`
        }}
      </v-btn>
    </SectionCard>
    <NoiseEffect
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
