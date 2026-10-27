<script setup lang="ts">
import { computed } from 'vue'

import type { AiProvider } from '@/api/ai'
import { isReady } from '@/ai'

/**
 * The switch that turns AI on, for the provider that is chosen. AI is off until it is turned on,
 * and only a provider that is set up with a model (and a key, if it takes one) can be asked.
 * Turning it on for this one while AresGate asks another moves it here. Everything in AresGate
 * works without AI.
 */
const props = defineProps<{
  /** The provider whose settings are shown. */
  provider: AiProvider
  enabled: boolean
  /** The provider AresGate asks, if one is chosen. */
  asking: AiProvider | undefined
  busy: boolean
  /** Why the last change was refused, if it was. */
  failure: string | null
}>()
const emit = defineEmits<{ change: [choice: { enabled: boolean; provider: string | null }] }>()

const ready = computed(() => isReady(props.provider))
/** On for this provider: the switch is about the provider that is shown. */
const on = computed(() => props.enabled && props.asking?.key === props.provider.key)
/** AI is on, but with another provider. */
const elsewhere = computed(() => (props.enabled && props.asking && !on.value ? props.asking : null))

/** Turning it off is only possible where it is on, which is for the provider that is shown. */
function turn(value: boolean | null) {
  emit('change', { enabled: value === true, provider: props.provider.key })
}
</script>

<template>
  <div class="use" data-test="ai-use">
    <v-switch
      :model-value="on"
      :label="`Use AI with ${provider.label}`"
      color="primary"
      inset
      hide-details
      :disabled="busy || (!ready && !on)"
      data-test="ai-enabled"
      @update:model-value="turn"
    />
    <p class="use__hint text-body-medium text-medium-emphasis" data-test="ai-use-hint">
      <template v-if="!ready && !on">
        Save {{ provider.label }} first: it needs a model and, if it takes one, an API key.
      </template>
      <template v-else-if="elsewhere">
        AI is on with {{ elsewhere.label }}. Turning this on asks {{ provider.label }} instead.
      </template>
      <template v-else>
        When it is on, AresGate asks it to read incidents and answer questions about your network.
        It only gives opinions: it never acts on its own, and everything works without it.
      </template>
    </p>
    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="compact"
      data-test="ai-use-failure"
    >
      {{ failure }}
    </v-alert>
  </div>
</template>

<style scoped>
.use {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.use__hint {
  margin: 0;
  padding-inline-start: 3.5rem;
}

@media (max-width: 599.98px) {
  .use__hint {
    padding-inline-start: 0;
  }
}
</style>
