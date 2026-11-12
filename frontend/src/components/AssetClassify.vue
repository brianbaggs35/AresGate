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
} from '@/api/assets'
import { errorMessage } from '@/api/client'
import { kindIcon } from '@/assetKinds'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Where the owner says what an asset is and what it is for. The programs list a hardware address
 * and a maker; only the owner knows that this box is the router and that one is the camera over
 * the front door. What is said is shown wherever the asset is (the Assets list, the devices an
 * incident went through) and goes to the analyst, which reads a camera that calls a stranger
 * differently from a laptop that browses. Where the name or the maker suggests a kind it is
 * offered, never applied.
 */
const props = defineProps<{ asset: Asset }>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()
const MAX_PURPOSE = 200

const groups = ref<AssetKindGroup[]>([])
const kind = ref<string | null>(props.asset.profile?.kind ?? null)
const purpose = ref(props.asset.profile?.purpose ?? '')
const saving = ref(false)
const failure = ref<string | null>(null)
const saved = ref(false)

/** Starts again from what is kept, for another asset or after a change was made elsewhere. */
function reset(said: AssetProfile | null) {
  kind.value = said?.kind ?? null
  purpose.value = said?.purpose ?? ''
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
    purpose.value.trim() !== (props.asset.profile?.purpose ?? ''),
)
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
      classifyAsset(props.asset.key, kind.value as string, said, token),
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
          @click="kind = suggestion"
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
          @click="kind = item.key"
        >
          {{ item.label }}
        </v-btn>
      </div>
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
      <span
        v-if="saved && !dirty"
        class="text-body-medium text-medium-emphasis"
        role="status"
        data-test="asset-classify-saved"
        >Saved.</span
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
