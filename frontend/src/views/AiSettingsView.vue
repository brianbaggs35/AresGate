<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchAi, useAi, type Ai, type AiProvider } from '@/api/ai'
import { errorMessage } from '@/api/client'
import AiProviderCard from '@/components/AiProviderCard.vue'
import AiUseCard from '@/components/AiUseCard.vue'
import LoadError from '@/components/LoadError.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const ai = ref<Ai | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const busy = ref(false)
const failure = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    ai.value = await session.call(fetchAi)
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
    // What the page shows is what it was before: the switch and the choice go back.
    await load()
  } finally {
    busy.value = false
  }
}

/** A provider changed (kept, tested, asked for its models): the page shows it as it is now. */
function replace(provider: AiProvider) {
  const current = ai.value as Ai
  ai.value = {
    ...current,
    providers: current.providers.map((item) => (item.key === provider.key ? provider : item)),
  }
}

/** Removing a provider can turn AI off, so the page asks how things are. */
async function removed() {
  await load()
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
  <template v-else-if="ai">
    <AiUseCard
      :enabled="ai.enabled"
      :provider="ai.provider"
      :providers="ai.providers"
      :busy="busy"
      :failure="failure"
      @change="choose"
    />
    <AiProviderCard
      v-for="provider in ai.providers"
      :key="provider.key"
      :provider="provider"
      :priced-as-of="ai.priced_as_of"
      @changed="replace"
      @removed="removed"
    />
  </template>
  <v-skeleton-loader v-else type="card, card" />
</template>
