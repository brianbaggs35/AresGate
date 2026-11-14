<script setup lang="ts">
import { Check, Sparkles, Undo2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import {
  classifyAsset,
  fetchKinds,
  unclassifyAsset,
  type Asset,
  type AssetKindGroup,
  type AssetProfile,
  type Importance,
} from '@/api/assets'
import { errorMessage } from '@/api/client'
import { kindIcon } from '@/assetKinds'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Where the owner says what an asset is and what it is for. The programs list a hardware address
 * and a maker; only the owner knows that this box is the router and that one is the camera over
 * the front door. What is said is shown wherever the asset is (the Assets list, the devices an
 * incident went through) and goes to the analyst, which reads a camera that calls a stranger
 * differently from a laptop that browses. Where the name or the maker suggests a kind it is
 * offered, never applied. How much it matters ranks the threats that touch it: a kind that usually
 * matters (the NAS that holds the backups, the router) offers its level when it is first picked,
 * and a guest's device or a gadget says that a threat that touched only it takes more proof.
 */
const props = defineProps<{ asset: Asset }>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()
const MAX_PURPOSE = 200
const LEVELS: readonly { key: Importance; label: string }[] = [
  { key: 'normal', label: 'Normal' },
  { key: 'important', label: 'Important' },
  { key: 'critical', label: 'Critical' },
]

const groups = ref<AssetKindGroup[]>([])
const kind = ref<string | null>(props.asset.profile?.kind ?? null)
const purpose = ref(props.asset.profile?.purpose ?? '')
const importance = ref<Importance>(props.asset.profile?.importance ?? 'normal')
// Whether the owner has chosen how much it matters, which a kind's own offer then leaves alone.
const chosen = ref(props.asset.profile !== null)
const saving = ref(false)
const failure = ref<string | null>(null)
const saved = ref(false)

/** Starts again from what is kept, for another asset or after a change was made elsewhere. */
function reset(said: AssetProfile | null) {
  kind.value = said?.kind ?? null
  purpose.value = said?.purpose ?? ''
  importance.value = said?.importance ?? 'normal'
  chosen.value = said !== null
}
watch(
  () => props.asset.key,
  () => {
    reset(props.asset.profile)
    saved.value = false
    failure.value = null
  },
)
watch(() => props.asset.profile, reset)

onMounted(async () => {
  try {
    groups.value = await session.call(() => fetchKinds())
  } catch (error) {
    failure.value = errorMessage(error)
  }
})

const dirty = computed(
  () =>
    kind.value !== (props.asset.profile?.kind ?? null) ||
    purpose.value.trim() !== (props.asset.profile?.purpose ?? '') ||
    importance.value !== (props.asset.profile?.importance ?? 'normal'),
)
const picked = computed(() =>
  groups.value.flatMap((group) => group.kinds).find((item) => item.key === kind.value),
)
/** Says what the kind chosen usually means for how much it matters, if it says anything. */
const note = computed(() => {
  if (picked.value?.lowers && importance.value === 'normal') {
    return 'A threat that touched only this kind of device needs more proof to be shown to you, unless you say it matters.'
  }
  if (picked.value && picked.value.importance !== 'normal' && !chosen.value) {
    return `A ${picked.value.label.toLowerCase()} usually matters: ${picked.value.importance} was filled in for you.`
  }
  return null
})

/** Picks a kind, and what usually goes with it for how much it matters, unless that was chosen. */
function pick(key: string) {
  kind.value = key
  const found = groups.value.flatMap((group) => group.kinds).find((item) => item.key === key)
  if (found && !chosen.value) importance.value = found.importance
}

function matters(value: Importance) {
  importance.value = value
  chosen.value = true
}
const suggestion = computed(() =>
  props.asset.profile === null && kind.value === null ? props.asset.suggested_kind : null,
)

/** Only reachable with a kind chosen: the button is disabled until then. */
async function save() {
  saving.value = true
  failure.value = null
  saved.value = false
  try {
    const said = purpose.value.trim() || null
    await session.change((token) =>
      classifyAsset(props.asset.key, kind.value as string, said, importance.value, token),
    )
    saved.value = true
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

async function clear() {
  saving.value = true
  failure.value = null
  saved.value = false
  try {
    await session.change((token) => unclassifyAsset(props.asset.key, token))
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <SectionCard
    title="What is it?"
    description="Say what this is and what it is for. It is shown wherever the device turns up, and the analyst reads it too."
    data-test="asset-classify"
  >
    <v-alert
      v-if="suggestion"
      type="info"
      variant="tonal"
      density="comfortable"
      :icon="Sparkles"
      class="mb-4"
      data-test="asset-suggestion"
    >
      <div class="suggestion">
        <span>
          Its name or maker suggests it is a
          <strong>{{ asset.suggested_label?.toLowerCase() }}</strong
          >.
        </span>
        <v-btn
          size="small"
          variant="tonal"
          data-test="asset-suggestion-use"
          @click="pick(suggestion)"
        >
          Use that
        </v-btn>
      </div>
    </v-alert>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="comfortable"
      class="mb-4"
      data-test="asset-classify-failure"
    >
      {{ failure }}
    </v-alert>

    <fieldset v-for="group in groups" :key="group.key" class="group">
      <legend class="text-label-large text-medium-emphasis">{{ group.label }}</legend>
      <div class="kinds">
        <v-btn
          v-for="item in group.kinds"
          :key="item.key"
          :prepend-icon="kindIcon(item.key)"
          :variant="kind === item.key ? 'flat' : 'outlined'"
          :color="kind === item.key ? 'primary' : undefined"
          :aria-pressed="kind === item.key"
          size="small"
          data-test="asset-kind-choice"
          @click="pick(item.key)"
        >
          {{ item.label }}
        </v-btn>
      </div>
    </fieldset>

    <fieldset class="matters" data-test="asset-importance">
      <legend class="text-label-large text-medium-emphasis">How much does it matter?</legend>
      <ChoiceToggle
        :model-value="importance"
        :options="LEVELS"
        label="How much it matters"
        name="asset-importance-choice"
        @update:model-value="matters"
      />
      <p class="text-body-medium text-medium-emphasis mt-2 mb-0">
        Threats that touch what matters come first, and are shown at a lower bar. The analyst is
        told too.
      </p>
      <p v-if="note" class="text-body-medium mt-1 mb-0" data-test="asset-importance-note">
        {{ note }}
      </p>
    </fieldset>

    <v-text-field
      v-model="purpose"
      label="What it is for"
      placeholder="Watches the front door"
      hint="In your own words, if you like. Optional."
      persistent-hint
      :counter="MAX_PURPOSE"
      :maxlength="MAX_PURPOSE"
      class="mt-4"
      data-test="asset-purpose"
    />

    <div class="actions">
      <v-btn
        color="primary"
        :prepend-icon="Check"
        :loading="saving"
        :disabled="kind === null || !dirty"
        data-test="asset-classify-save"
        @click="save"
      >
        Save
      </v-btn>
      <v-btn
        v-if="asset.profile"
        variant="text"
        :prepend-icon="Undo2"
        :disabled="saving"
        data-test="asset-classify-clear"
        @click="clear"
      >
        Take it back
      </v-btn>
      <output
        v-if="saved && !dirty"
        class="text-body-medium text-medium-emphasis"
        data-test="asset-classify-saved"
        >Saved.</output
      >
    </div>
  </SectionCard>
</template>

<style scoped>
.suggestion {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.group {
  margin: 0 0 1rem;
  padding: 0;
  border: 0;
}

.group legend {
  margin-bottom: 0.5rem;
  padding: 0;
}

.matters {
  margin: 1rem 0 0;
  padding: 0;
  border: 0;
}

.matters legend {
  margin-bottom: 0.5rem;
  padding: 0;
}

.kinds {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}
</style>
