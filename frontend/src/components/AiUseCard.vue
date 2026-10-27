<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { computed } from 'vue'

import type { AiProvider } from '@/api/ai'
import { isReady } from '@/ai'
import SectionCard from '@/components/SectionCard.vue'

/**
 * Whether AresGate uses AI at all, and which provider it asks. AI is off until it is turned on,
 * and only a provider that is set up with a model (and a key, if it takes one) can be asked.
 * Everything in AresGate works without it.
 */
const props = defineProps<{
  enabled: boolean
  provider: string | null
  providers: readonly AiProvider[]
  busy: boolean
  /** Why the last change was refused, if it was. */
  failure: string | null
}>()
const emit = defineEmits<{ change: [choice: { enabled: boolean; provider: string | null }] }>()

const ready = computed(() => props.providers.filter(isReady))
const items = computed(() =>
  ready.value.map((item) => ({
    value: item.key,
    title: item.label,
    props: { subtitle: item.model },
  })),
)

function turn(on: boolean | null) {
  const enabled = on === true
  // Turning it on with one provider to ask asks that one.
  const [first, second] = ready.value
  const only = first && !second ? first.key : null
  emit('change', { enabled, provider: props.provider ?? (enabled ? only : null) })
}

function choose(provider: string | null) {
  emit('change', { enabled: props.enabled, provider })
}
</script>

<template>
  <SectionCard
    title="Use AI"
    description="When AI is on, AresGate can ask the provider you choose to read incidents and answer questions about your network. It only gives opinions: it never acts on its own, and everything works without it."
    data-test="ai-use-card"
  >
    <template #actions>
      <v-icon :icon="Sparkles" :color="enabled ? 'primary' : undefined" aria-hidden="true" />
    </template>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      data-test="ai-use-failure"
    >
      {{ failure }}
    </v-alert>

    <div class="ai-use">
      <v-switch
        :model-value="enabled"
        label="Use AI"
        color="primary"
        inset
        hide-details
        :disabled="busy || (ready.length === 0 && !enabled)"
        data-test="ai-enabled"
        @update:model-value="turn"
      />
      <v-select
        :model-value="provider"
        label="Ask"
        :items="items"
        :disabled="busy || ready.length === 0"
        hide-details
        clearable
        data-test="ai-provider"
        @update:model-value="choose"
      />
      <!-- Not the field's own hint, which is dimmed with the field while it is disabled. -->
      <p
        v-if="ready.length === 0"
        class="ai-use__hint text-body-medium text-medium-emphasis"
        data-test="ai-use-hint"
      >
        Set up a provider below first: it needs a model and, if it takes one, an API key.
      </p>
    </div>
  </SectionCard>
</template>

<style scoped>
.ai-use {
  display: grid;
  grid-template-columns: minmax(0, 14rem) minmax(0, 1fr);
  align-items: start;
  gap: 1rem 1.5rem;
}

.ai-use__hint {
  grid-column: 1 / -1;
  margin: 0;
}

@media (max-width: 599.98px) {
  .ai-use {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
