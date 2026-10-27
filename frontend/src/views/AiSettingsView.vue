<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { fetchAi, useAi, type Ai, type AiProvider } from '@/api/ai'
import { errorMessage } from '@/api/client'
import { useNote } from '@/ai'
import AiProviderForm from '@/components/AiProviderForm.vue'
import AiProviderPicker from '@/components/AiProviderPicker.vue'
import AiUseSwitch from '@/components/AiUseSwitch.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > AI: one card in which to choose where the AI runs and set that provider up. Only the
 * chosen provider's settings are shown, and what was typed into one stays while another is looked
 * at. AI is optional: everything in AresGate works the same without it.
 */
const session = useSessionStore()

const ai = ref<Ai | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const busy = ref(false)
const failure = ref<string | null>(null)
/** The provider whose settings are shown: the one being asked, else one that is set up. */
const chosen = ref<string | null>(null)

const current = computed(() => ai.value?.providers.find((item) => item.key === chosen.value))
const asking = computed(() => ai.value?.providers.find((item) => item.key === ai.value?.provider))

async function load() {
  loading.value = true
  loadError.value = null
  try {
    ai.value = await session.call(fetchAi)
    chosen.value ??=
      ai.value.provider ?? ai.value.providers.find((item) => item.configured)?.key ?? null
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function choose(choice: { enabled: boolean; provider: string | null }) {
  busy.value = true
  failure.value = null
  try {
    ai.value = await session.change((token) => useAi(choice, token))
  } catch (error) {
    failure.value = errorMessage(error)
    // What the page shows is what it was before: the switch goes back.
    await load()
  } finally {
    busy.value = false
  }
}

/** A provider changed (kept, tested, asked for its models): the page shows it as it is now. */
function replace(provider: AiProvider) {
  const known = ai.value as Ai
  ai.value = {
    ...known,
    providers: known.providers.map((item) => (item.key === provider.key ? provider : item)),
  }
}

onMounted(load)
</script>

<template>
  <LoadError
    v-if="loadError && !ai"
    :message="loadError"
    :loading="loading"
    data-test="ai-error"
    @retry="load"
  />
  <SectionCard
    v-else-if="ai"
    title="AI provider"
    description="It's optional. AresGate works the same without it, and with it you can have incidents read and explained, and ask about your network. It only gives opinions: it never acts on its own."
    data-test="ai-card"
  >
    <template #actions>
      <v-chip
        :color="ai.enabled ? 'success' : undefined"
        :variant="ai.enabled ? 'tonal' : 'outlined'"
        :prepend-icon="Sparkles"
        data-test="ai-state"
      >
        {{ useNote(ai) }}
      </v-chip>
    </template>

    <div class="ai">
      <AiProviderPicker
        v-model="chosen"
        :providers="ai.providers"
        :asking="ai.enabled ? ai.provider : null"
      />
      <p
        v-if="!current"
        class="text-body-medium text-medium-emphasis ai__choose"
        data-test="ai-choose"
      >
        Choose one to set it up. You can set up more than one and switch between them.
      </p>
      <KeepAlive>
        <AiProviderForm
          v-if="current"
          :key="current.key"
          :provider="current"
          :priced-as-of="ai.priced_as_of"
          :free-models-as-of="ai.free_models_as_of"
          @changed="replace"
          @removed="load"
        >
          <AiUseSwitch
            :provider="current"
            :enabled="ai.enabled"
            :asking="asking"
            :busy="busy"
            :failure="failure"
            @change="choose"
          />
        </AiProviderForm>
      </KeepAlive>
    </div>
  </SectionCard>
  <v-skeleton-loader v-else type="card, card" />
</template>

<style scoped>
.ai {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.ai__choose {
  margin: 0;
}
</style>
